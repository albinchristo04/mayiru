const https = require('https');
const fs = require('fs');
const { URL } = require('url');

// ─── Read target URL from env or CLI arg ───────────────────────────────────
const PAGE_URL = process.env.STREAMTP_URL || process.argv[2];

if (!PAGE_URL) {
    console.error('ERROR: No URL provided. Set STREAMTP_URL env var or pass URL as first argument.');
    process.exit(1);
}

// ─── Core scraper ──────────────────────────────────────────────────────────
function getStreamtpUrl(pageUrl) {
    return new Promise((resolve, reject) => {
        const urlObject = new URL(pageUrl);
        const targetHostname = urlObject.hostname;

        const options = {
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
                'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8,en-US;q=0.7',
                'Referer': `https://${targetHostname}/`,
            }
        };

        https.get(pageUrl, options, (res) => {
            let htmlString = '';

            if (res.statusCode !== 200) {
                let errorBody = '';
                res.on('data', (chunk) => { errorBody += chunk; });
                res.on('end', () => {
                    reject(new Error(`HTTP ${res.statusCode} ${res.statusMessage}\nBody: ${errorBody}`));
                });
                return;
            }

            res.setEncoding('utf8');
            res.on('data', (chunk) => { htmlString += chunk; });
            res.on('end', () => {
                try {
                    // 1. Find the encoded data array
                    const mainLogicRegex = /var\s+playbackURL\s*=\s*"",\s*(\w+)\s*=\s*\[\][^;]*;\s*\1\s*=\s*(\[\[[\s\S]*?\]\]);/;
                    const mainMatch = htmlString.match(mainLogicRegex);
                    if (!mainMatch) {
                        reject(new Error('Could not find data array structure in page HTML.'));
                        return;
                    }
                    const capturedArrayVariableName = mainMatch[1];
                    const dataArrayString = mainMatch[2];

                    // 2. Find function names used to build decryption key k
                    const kFunctionsRegex = /var\s+k\s*=\s*(\w+)\s*\(\s*\)\s*\+\s*(\w+)\s*\(\s*\);/;
                    const kMatch = htmlString.match(kFunctionsRegex);
                    if (!kMatch) {
                        reject(new Error('Could not find k function names in page HTML.'));
                        return;
                    }
                    const capturedK1FunctionName = kMatch[1];
                    const capturedK2FunctionName = kMatch[2];

                    // 3. Extract numeric return values of both functions
                    const k1Regex = new RegExp(`function\\s+${capturedK1FunctionName}\\s*\\(\\)\\s*\\{\\s*return\\s*(\\d+);?\\s*\\}`);
                    const k2Regex = new RegExp(`function\\s+${capturedK2FunctionName}\\s*\\(\\)\\s*\\{\\s*return\\s*(\\d+);?\\s*\\}`);

                    const k1Match = htmlString.match(k1Regex);
                    const k2Match = htmlString.match(k2Regex);

                    if (!k1Match) { reject(new Error(`Could not find return value for function '${capturedK1FunctionName}'.`)); return; }
                    if (!k2Match) { reject(new Error(`Could not find return value for function '${capturedK2FunctionName}'.`)); return; }

                    const k1 = parseInt(k1Match[1], 10);
                    const k2 = parseInt(k2Match[1], 10);
                    const k = k1 + k2;

                    if (k === 0) {
                        reject(new Error(`Decryption key k=0 (k1=${k1}, k2=${k2}) — likely a parsing error.`));
                        return;
                    }

                    // 4. Parse + sort + decode the array
                    let dataArray;
                    try {
                        dataArray = new Function('return ' + dataArrayString)();
                    } catch (e) {
                        reject(new Error(`Failed to parse data array: ${e.message}`));
                        return;
                    }

                    dataArray.sort((a, b) => a[0] - b[0]);

                    let playbackURL = '';
                    dataArray.forEach(e => {
                        if (Array.isArray(e) && e.length >= 2 && typeof e[1] === 'string') {
                            const decoded = Buffer.from(e[1], 'base64').toString('latin1');
                            const digits = decoded.replace(/\D/g, '');
                            if (digits) {
                                playbackURL += String.fromCharCode(parseInt(digits) - k);
                            }
                        }
                    });

                    resolve(playbackURL);

                } catch (error) {
                    reject(new Error(`Parse/decrypt error: ${error.message}`));
                }
            });

        }).on('error', (err) => {
            reject(new Error(`HTTPS request error: ${err.message}`));
        });
    });
}

// ─── Main runner ───────────────────────────────────────────────────────────
(async () => {
    const startedAt = new Date().toISOString();
    console.log(`\n[${startedAt}] Fetching: ${PAGE_URL}\n`);

    let result;

    try {
        const playbackURL = await getStreamtpUrl(PAGE_URL);

        result = {
            success: true,
            source_url: PAGE_URL,
            playback_url: playbackURL,
            fetched_at: startedAt,
        };

        console.log('✅ Playback URL found:', playbackURL);

    } catch (err) {
        result = {
            success: false,
            source_url: PAGE_URL,
            error: err.message,
            fetched_at: startedAt,
        };

        console.error('❌ Failed:', err.message);
    }

    // ─── Write output JSON ────────────────────────────────────────────────
    const outputPath = process.env.OUTPUT_FILE || 'output.json';
    fs.writeFileSync(outputPath, JSON.stringify(result, null, 2), 'utf8');
    console.log(`\n📄 Result saved to: ${outputPath}`);
    console.log(JSON.stringify(result, null, 2));

    // Exit with error code if scraping failed (useful for CI)
    if (!result.success) process.exit(1);
})();
