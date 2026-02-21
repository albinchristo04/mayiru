const https = require('https');
const http = require('http');
const fs = require('fs');
const { URL } = require('url');

// ─── Read target URL from env or CLI arg ───────────────────────────────────
const PAGE_URL = process.env.STREAMTP_URL || process.argv[2];

if (!PAGE_URL) {
    console.error('ERROR: No URL provided. Set STREAMTP_URL env var or pass URL as first argument.');
    process.exit(1);
}

// ─── HTTP fetch with automatic redirect following ──────────────────────────
function fetchWithRedirects(pageUrl, headers, redirectCount = 0) {
    return new Promise((resolve, reject) => {
        if (redirectCount > 10) {
            return reject(new Error('Too many redirects (>10)'));
        }

        const urlObject = new URL(pageUrl);
        const transport = urlObject.protocol === 'https:' ? https : http;

        const options = {
            hostname: urlObject.hostname,
            path: urlObject.pathname + urlObject.search,
            headers,
        };

        transport.get(options, (res) => {
            // Follow 301 / 302 / 303 / 307 / 308 redirects
            if ([301, 302, 303, 307, 308].includes(res.statusCode)) {
                const location = res.headers['location'];
                if (!location) {
                    return reject(new Error(`Redirect with no Location header (status ${res.statusCode})`));
                }
                const nextUrl = new URL(location, pageUrl).toString();
                console.log(`  ↩ Redirect ${res.statusCode} → ${nextUrl}`);
                res.resume(); // discard body
                return fetchWithRedirects(nextUrl, headers, redirectCount + 1)
                    .then(resolve).catch(reject);
            }

            if (res.statusCode !== 200) {
                let errorBody = '';
                res.on('data', (chunk) => { errorBody += chunk; });
                res.on('end', () => {
                    reject(new Error(`HTTP ${res.statusCode} ${res.statusMessage}\nBody: ${errorBody}`));
                });
                return;
            }

            let html = '';
            res.setEncoding('utf8');
            res.on('data', (chunk) => { html += chunk; });
            res.on('end', () => resolve(html));

        }).on('error', (err) => reject(new Error(`Request error: ${err.message}`)));
    });
}

// ─── Core scraper ──────────────────────────────────────────────────────────
async function getStreamtpUrl(pageUrl) {
    const urlObject = new URL(pageUrl);
    const targetHostname = urlObject.hostname;

    const headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8,en-US;q=0.7',
        'Referer': `https://${targetHostname}/`,
    };

    const htmlString = await fetchWithRedirects(pageUrl, headers);

    // 1. Find the encoded data array
    const mainLogicRegex = /var\s+playbackURL\s*=\s*"",\s*(\w+)\s*=\s*\[\][^;]*;\s*\1\s*=\s*(\[\[[\s\S]*?\]\]);/;
    const mainMatch = htmlString.match(mainLogicRegex);
    if (!mainMatch) throw new Error('Could not find data array structure in page HTML.');
    const dataArrayString = mainMatch[2];

    // 2. Find function names used to build decryption key k
    const kFunctionsRegex = /var\s+k\s*=\s*(\w+)\s*\(\s*\)\s*\+\s*(\w+)\s*\(\s*\);/;
    const kMatch = htmlString.match(kFunctionsRegex);
    if (!kMatch) throw new Error('Could not find k function names in page HTML.');
    const [, k1FnName, k2FnName] = kMatch;

    // 3. Extract numeric return values of both functions
    const k1Match = htmlString.match(new RegExp(`function\\s+${k1FnName}\\s*\\(\\)\\s*\\{\\s*return\\s*(\\d+);?\\s*\\}`));
    const k2Match = htmlString.match(new RegExp(`function\\s+${k2FnName}\\s*\\(\\)\\s*\\{\\s*return\\s*(\\d+);?\\s*\\}`));
    if (!k1Match) throw new Error(`Could not find return value for function '${k1FnName}'.`);
    if (!k2Match) throw new Error(`Could not find return value for function '${k2FnName}'.`);

    const k = parseInt(k1Match[1], 10) + parseInt(k2Match[1], 10);
    if (k === 0) throw new Error(`Decryption key k=0 — likely a parsing error.`);

    // 4. Parse, sort and decode the array
    let dataArray;
    try {
        dataArray = new Function('return ' + dataArrayString)();
    } catch (e) {
        throw new Error(`Failed to parse data array: ${e.message}`);
    }

    dataArray.sort((a, b) => a[0] - b[0]);

    let playbackURL = '';
    dataArray.forEach(e => {
        if (Array.isArray(e) && e.length >= 2 && typeof e[1] === 'string') {
            const decoded = Buffer.from(e[1], 'base64').toString('latin1');
            const digits = decoded.replace(/\D/g, '');
            if (digits) playbackURL += String.fromCharCode(parseInt(digits) - k);
        }
    });

    return playbackURL;
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

    // Write output JSON
    const outputPath = process.env.OUTPUT_FILE || 'output.json';
    fs.writeFileSync(outputPath, JSON.stringify(result, null, 2), 'utf8');
    console.log(`\n📄 Result saved to: ${outputPath}`);
    console.log(JSON.stringify(result, null, 2));

    if (!result.success) process.exit(1);
})();
