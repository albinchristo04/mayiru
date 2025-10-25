#!/usr/bin/env python3
"""
Standalone DLHD extractor CLI module
- Usage: python dlhd_extractor_cli.py --url <STREAM_PAGE_URL> [--output ./out.json] [--force]
- Designed to run in CI (GitHub Actions). Prints JSON to stdout and writes to an output file.

Dependencies:
- aiohttp
- aiohttp-proxy
- zstandard

Install: pip install aiohttp aiohttp-proxy zstandard

Environment variables supported:
- DLHD_PROXIES: optional, comma-separated list of proxy URLs (e.g. http://user:pass@host:port)
- DLHD_REQUEST_HEADERS: optional, JSON string of extra headers to include
- OUTPUT_PATH: optional, path to write the JSON output (default: ./dlhd_result.json)

Exit codes:
- 0 success
- 2 extractor-specific failure
- 3 invalid arguments / runtime error

"""

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import List, Dict, Any

# ---- Paste of the DLHD class follows (kept mostly intact, minor path/cache handling tweaks) ----

import re
import base64
import os as _os
import gzip
import zlib
import random
from urllib.parse import urlparse, quote_plus, urljoin
import aiohttp
from aiohttp import ClientSession, ClientTimeout, TCPConnector
from aiohttp_proxy import ProxyConnector
import zstandard

logger = logging.getLogger(__name__)

class ExtractorError(Exception):
    pass

class DLHDExtractor:
    """DLHD Extractor con sessione persistente e gestione anti-bot avanzata"""

    def __init__(self, request_headers: dict = None, proxies: List[str] = None, cache_file: str = None):
        self.request_headers = request_headers or {}
        self.base_headers = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        }
        self.session = None
        self.mediaflow_endpoint = "hls_manifest_proxy"
        self._cached_base_url = None
        self._iframe_context = None
        self._session_lock = asyncio.Lock()
        self.proxies = proxies or []
        self._extraction_locks = {}
        # store cache near the running script unless otherwise specified
        if cache_file:
            self.cache_file = cache_file
        else:
            try:
                base_dir = _os.path.dirname(__file__)
            except Exception:
                base_dir = os.getcwd()
            self.cache_file = _os.path.join(base_dir, '.dlhd_cache')
        self._stream_data_cache = self._load_cache()

    def _load_cache(self):
        try:
            if _os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    encoded_data = f.read()
                    if not encoded_data:
                        return {}
                    decoded_data = base64.b64decode(encoded_data).decode('utf-8')
                    return json.loads(decoded_data)
        except Exception as e:
            logger.warning(f"Unable to load cache ({self.cache_file}): {e}")
        return {}

    def _get_random_proxy(self):
        return random.choice(self.proxies) if self.proxies else None

    async def _get_session(self):
        if self.session is None or self.session.closed:
            timeout = ClientTimeout(total=60, connect=30, sock_read=30)
            proxy = self._get_random_proxy()
            if proxy:
                connector = ProxyConnector.from_url(proxy, ssl=False)
            else:
                connector = TCPConnector(limit=10, limit_per_host=3, keepalive_timeout=30, enable_cleanup_closed=True, force_close=False, use_dns_cache=True)
            self.session = ClientSession(timeout=timeout, connector=connector, headers=self.base_headers, cookie_jar=aiohttp.CookieJar())
        return self.session

    def _save_cache(self):
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json_data = json.dumps(self._stream_data_cache)
                encoded_data = base64.b64encode(json_data.encode('utf-8')).decode('utf-8')
                f.write(encoded_data)
        except Exception as e:
            logger.warning(f"Unable to save cache: {e}")

    def _get_headers_for_url(self, url: str, base_headers: dict) -> dict:
        headers = base_headers.copy()
        parsed_url = urlparse(url)
        if "newkso.ru" in parsed_url.netloc:
            if self._iframe_context:
                iframe_origin = f"https://{urlparse(self._iframe_context).netloc}"
                newkso_headers = {'User-Agent': self.base_headers.get('user-agent'), 'Referer': self._iframe_context, 'Origin': iframe_origin}
            else:
                newkso_origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
                newkso_headers = {'User-Agent': self.base_headers.get('user-agent'), 'Referer': newkso_origin, 'Origin': newkso_origin}
            headers.update(newkso_headers)
        return headers

    async def _handle_response_content(self, response: aiohttp.ClientResponse) -> str:
        content_encoding = response.headers.get('Content-Encoding')
        raw_body = await response.read()
        try:
            if content_encoding == 'zstd':
                dctx = zstandard.ZstdDecompressor()
                with dctx.stream_reader(raw_body) as reader:
                    decompressed_body = reader.read()
                return decompressed_body.decode(response.charset or 'utf-8')
            elif content_encoding == 'gzip':
                decompressed_body = gzip.decompress(raw_body)
                return decompressed_body.decode(response.charset or 'utf-8')
            elif content_encoding == 'deflate':
                decompressed_body = zlib.decompress(raw_body)
                return decompressed_body.decode(response.charset or 'utf-8')
            else:
                return raw_body.decode(response.charset or 'utf-8')
        except Exception as e:
            raise ExtractorError(f"Decompression failed: {e}")

    async def _make_robust_request(self, url: str, headers: dict = None, retries=3, initial_delay=2):
        final_headers = self._get_headers_for_url(url, headers or {})
        final_headers['Accept-Encoding'] = 'gzip, deflate, br, zstd'
        for attempt in range(retries):
            try:
                session = await self._get_session()
                async with session.get(url, headers=final_headers, ssl=False, auto_decompress=False) as response:
                    response.raise_for_status()
                    content = await self._handle_response_content(response)
                    class MockResponse:
                        def __init__(self, text_content, status, headers_dict, url):
                            self._text = text_content
                            self.status = status
                            self.headers = headers_dict
                            self.url = url
                        async def text(self):
                            return self._text
                        def raise_for_status(self):
                            if self.status >= 400:
                                raise aiohttp.ClientResponseError(request_info=None, history=None, status=self.status)
                        async def json(self):
                            return json.loads(self._text)
                    return MockResponse(content, response.status, dict(response.headers), str(response.url))
            except (aiohttp.ClientConnectionError, aiohttp.ServerDisconnectedError, aiohttp.ClientPayloadError, asyncio.TimeoutError, OSError, ConnectionResetError) as e:
                if attempt == retries - 1:
                    if self.session and not self.session.closed:
                        try:
                            await self.session.close()
                        except Exception:
                            pass
                    self.session = None
                if attempt < retries - 1:
                    await asyncio.sleep(initial_delay * (2 ** attempt))
                else:
                    raise ExtractorError(f"All retries failed for {url}: {e}")
            except Exception as e:
                if 'zstd' in str(e).lower():
                    logger.critical("Zstd error: ensure zstandard is installed")
                if attempt == retries - 1:
                    raise ExtractorError(str(e))
        await asyncio.sleep(initial_delay)

    async def extract(self, url: str, force_refresh: bool = False, **kwargs) -> Dict[str, Any]:
        async def resolve_base_url(preferred_host: str = None) -> str:
            if self._cached_base_url and not force_refresh:
                return self._cached_base_url
            DOMAINS = ['https://daddylive.sx/', 'https://dlhd.dad/']
            for base in DOMAINS:
                try:
                    resp = await self._make_robust_request(base, retries=1)
                    final_url = str(resp.url)
                    if not final_url.endswith('/'):
                        final_url += '/'
                    self._cached_base_url = final_url
                    return final_url
                except Exception:
                    continue
            self._cached_base_url = DOMAINS[0]
            return DOMAINS[0]

        def extract_channel_id(u: str) -> str:
            patterns = [r'/premium(\d+)/mono\.m3u8$', r'/(?:watch|stream|cast|player)/stream-(\d+)\.php', r'watch\.php\?id=(\d+)', r'(?:%2F|/)stream-(\d+)\.php', r'stream-(\d+)\.php']
            for pattern in patterns:
                match = re.search(pattern, u, re.IGNORECASE)
                if match:
                    return match.group(1)
            return None

        async def get_stream_data(baseurl: str, initial_url: str, channel_id: str):
            def _extract_auth_params_dynamic(js: str):
                pattern = r'(?:const|var|let)\s+[A-Z0-9_]+\s*=\s*["\']([a-zA-Z0-9+/=]{50,})["\']'
                matches = re.finditer(pattern, js)
                for match in matches:
                    b64_data = match.group(1)
                    try:
                        json_data = base64.b64decode(b64_data).decode('utf-8')
                        obj_data = json.loads(json_data)
                        key_mappings = {
                            'auth_host': ['host', 'b_host', 'server', 'domain'],
                            'auth_php': ['script', 'b_script', 'php', 'path'],
                            'auth_ts': ['ts', 'b_ts', 'timestamp', 'time'],
                            'auth_rnd': ['rnd', 'b_rnd', 'random', 'nonce'],
                            'auth_sig': ['sig', 'b_sig', 'signature', 'sign']
                        }
                        result = {}
                        is_complete = True
                        for target_key, possible_names in key_mappings.items():
                            found_key = False
                            for name in possible_names:
                                if name in obj_data:
                                    try:
                                        decoded_value = base64.b64decode(obj_data[name]).decode('utf-8')
                                        result[target_key] = decoded_value
                                    except Exception:
                                        result[target_key] = obj_data[name]
                                    found_key = True
                                    break
                            if not found_key:
                                is_complete = False
                                break
                        if is_complete:
                            return result
                    except Exception:
                        continue
                return {}

            daddy_origin = urlparse(baseurl).scheme + "://" + urlparse(baseurl).netloc
            daddylive_headers = {'User-Agent': self.base_headers.get('user-agent'), 'Referer': baseurl, 'Origin': daddy_origin}
            resp1 = await self._make_robust_request(initial_url, headers=daddylive_headers)
            content1 = await resp1.text()
            player_links = re.findall(r'<button[^>]*data-url="([^"]+)"[^>]*>Player\s*\d+</button>', content1)
            if not player_links:
                raise ExtractorError("No player links found")
            iframe_url = None
            last_player_error = None
            for player_url in player_links:
                try:
                    if not player_url.startswith('http'):
                        player_url = urljoin(baseurl, player_url)
                    daddylive_headers['Referer'] = player_url
                    resp2 = await self._make_robust_request(player_url, headers=daddylive_headers)
                    content2 = await resp2.text()
                    iframes2 = re.findall(r'iframe src="([^\"]*)', content2)
                    if iframes2:
                        iframe_url = iframes2[0]
                        if not iframe_url.startswith('http'):
                            iframe_url = urljoin(player_url, iframe_url)
                        break
                except Exception as e:
                    last_player_error = e
                    continue
            if not iframe_url:
                if last_player_error:
                    raise ExtractorError(f"All player links failed: {last_player_error}")
                raise ExtractorError("No iframe found")
            self._iframe_context = iframe_url
            resp3 = await self._make_robust_request(iframe_url, headers=daddylive_headers)
            iframe_content = await resp3.text()
            try:
                channel_key = None
                channel_key_patterns = [r'const\s+CHANNEL_KEY\s*=\s*"([^"\']+)"', r'channelKey\s*=\s*"([^"\']+)"', r'(?:let|const)\s+channelKey\s*=\s*"([^"\']+)"', r'var\s+channelKey\s*=\s*"([^"\']+)"', r'channel_id\s*:\s*"([^"\']+)"']
                for pattern in channel_key_patterns:
                    match = re.search(pattern, iframe_content)
                    if match:
                        channel_key = match.group(1)
                        break
                params = _extract_auth_params_dynamic(iframe_content)
                auth_host = params.get('auth_host')
                auth_php = params.get('auth_php')
                auth_ts = params.get('auth_ts')
                auth_rnd = params.get('auth_rnd')
                auth_sig = params.get('auth_sig')
                missing_params = []
                if not channel_key:
                    missing_params.append('channel_key')
                if not auth_ts:
                    missing_params.append('auth_ts (timestamp)')
                if not auth_rnd:
                    missing_params.append('auth_rnd (random)')
                if not auth_sig:
                    missing_params.append('auth_sig (signature)')
                if not auth_host:
                    missing_params.append('auth_host (host)')
                if not auth_php:
                    missing_params.append('auth_php (script)')
                if missing_params:
                    raise ExtractorError(f"Missing params: {', '.join(missing_params)}")
                auth_sig_quoted = quote_plus(auth_sig)
                if auth_php:
                    normalized_auth_php = auth_php.strip().lstrip('/')
                    if normalized_auth_php == 'a.php':
                        auth_php = 'auth.php'
                base_auth_url = urljoin(auth_host, auth_php)
                auth_url = f'{base_auth_url}?channel_id={channel_key}&ts={auth_ts}&rnd={auth_rnd}&sig={auth_sig_quoted}'
                iframe_origin = f"https://{urlparse(iframe_url).netloc}"
                auth_headers = daddylive_headers.copy()
                auth_headers['Referer'] = iframe_url
                auth_headers['Origin'] = iframe_origin
                try:
                    await self._make_robust_request(auth_url, headers=auth_headers, retries=1)
                except Exception as auth_error:
                    if channel_id in self._stream_data_cache:
                        del self._stream_data_cache[channel_id]
                        self._save_cache()
                        return await get_stream_data(baseurl, initial_url, channel_id)
                    raise ExtractorError(f"Auth failed: {auth_error}")
                lookup_match = re.search(r"fetchWithRetry\(['\"](/server_lookup\.(?:js|php)\?channel_id=)['\"]", iframe_content)
                server_lookup_path = None
                if lookup_match:
                    server_lookup_path = lookup_match.group(1)
                else:
                    lookup_match_generic = re.search(r"['\"](/server_lookup\.(?:js|php)\?channel_id=)['\"]", iframe_content)
                    if lookup_match_generic:
                        server_lookup_path = lookup_match_generic.group(1)
                if not server_lookup_path:
                    raise ExtractorError("Unable to extract server lookup URL")
                server_lookup_url = f"https://{urlparse(iframe_url).netloc}{server_lookup_path}{channel_key}"
                try:
                    lookup_resp = await self._make_robust_request(server_lookup_url, headers=daddylive_headers)
                    server_data = await lookup_resp.json()
                    server_key = server_data.get('server_key')
                    if not server_key:
                        raise ExtractorError("No server_key in lookup response")
                except Exception as lookup_error:
                    raise ExtractorError(f"Server lookup failed: {lookup_error}")
                if server_key == 'top1/cdn':
                    clean_m3u8_url = f'https://top1.newkso.ru/top1/cdn/{channel_key}/mono.m3u8'
                elif '/' in server_key:
                    parts = server_key.split('/')
                    domain = parts[0]
                    clean_m3u8_url = f'https://{domain}.newkso.ru/{server_key}/{channel_key}/mono.m3u8'
                else:
                    clean_m3u8_url = f'https://{server_key}new.newkso.ru/{server_key}/{channel_key}/mono.m3u8'.replace('top2new', 'top1new')
                if "newkso.ru" in clean_m3u8_url:
                    stream_headers = {'User-Agent': daddylive_headers['User-Agent'], 'Referer': iframe_url, 'Origin': f'https://{urlparse(iframe_url).netloc}'}
                else:
                    stream_headers = {'User-Agent': daddylive_headers['User-Agent'], 'Referer': f'https://{urlparse(iframe_url).netloc}', 'Origin': f'https://{urlparse(iframe_url).netloc}'}
                result_data = {"destination_url": clean_m3u8_url, "request_headers": stream_headers, "mediaflow_endpoint": self.mediaflow_endpoint}
                self._stream_data_cache[channel_id] = result_data
                self._save_cache()
                return result_data
            except Exception as param_error:
                raise ExtractorError(f"Parameter extraction failed: {param_error}")

        try:
            channel_id = extract_channel_id(url)
            if not channel_id:
                raise ExtractorError(f"Unable to extract channel ID from {url}")
            if not force_refresh and channel_id in self._stream_data_cache:
                cached_data = self._stream_data_cache[channel_id]
                stream_url = cached_data.get('destination_url')
                stream_headers = cached_data.get('request_headers', {})
                is_valid = False
                if stream_url:
                    try:
                        async with aiohttp.ClientSession(timeout=ClientTimeout(total=10)) as validation_session:
                            async with validation_session.head(stream_url, headers=stream_headers, ssl=False) as response:
                                if response.status == 200:
                                    is_valid = True
                    except Exception:
                        is_valid = False
                if not is_valid:
                    if channel_id in self._stream_data_cache:
                        del self._stream_data_cache[channel_id]
                    self._save_cache()
                else:
                    try:
                        await self._make_robust_request(url, retries=1)
                    except Exception:
                        pass
                    return cached_data
            if channel_id not in self._extraction_locks:
                self._extraction_locks[channel_id] = asyncio.Lock()
            lock = self._extraction_locks[channel_id]
            async with lock:
                if channel_id in self._stream_data_cache:
                    return self._stream_data_cache[channel_id]
                baseurl = await resolve_base_url()
                return await get_stream_data(baseurl, url, channel_id)
        except Exception as e:
            raise ExtractorError(f"DLHD extraction failed: {e}")

    async def invalidate_cache_for_url(self, url: str):
        patterns = [r'/premium(\d+)/mono\.m3u8$', r'/(?:watch|stream|cast|player)/stream-(\d+)\.php', r'watch\.php\?id=(\d+)', r'(?:%2F|/)stream-(\d+)\.php', r'stream-(\d+)\.php']
        channel_id = None
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                channel_id = match.group(1)
                break
        if channel_id and channel_id in self._stream_data_cache:
            del self._stream_data_cache[channel_id]
            self._save_cache()

    async def close(self):
        if self.session and not self.session.closed:
            try:
                await self.session.close()
            except Exception:
                pass
        self.session = None

# ---- End class ----

# CLI wrapper

async def run_extraction(url: str, output_path: str, force: bool, proxies: List[str], extra_headers: Dict[str, str]):
    extractor = DLHDExtractor(request_headers=extra_headers, proxies=proxies)
    try:
        result = await extractor.extract(url, force_refresh=force)
        output = {
            'success': True,
            'input_url': url,
            'result': result
        }
        # write to file
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Unable to write output file: {e}")
        # also print to stdout for Github Actions capture
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except ExtractorError as ee:
        output = {'success': False, 'input_url': url, 'error': str(ee)}
        print(json.dumps(output, ensure_ascii=False))
        return 2
    except Exception as e:
        output = {'success': False, 'input_url': url, 'error': str(e)}
        print(json.dumps(output, ensure_ascii=False))
        return 3
    finally:
        await extractor.close()

def parse_proxies(env_value: str):
    if not env_value:
        return []
    return [p.strip() for p in env_value.split(',') if p.strip()]

def main():
    parser = argparse.ArgumentParser(description='DLHD extractor CLI')
    parser.add_argument('--url', required=True, help='Page URL that contains the stream (e.g. https://daddylive.sx/watch.php?id=123)')
    parser.add_argument('--output', default=os.environ.get('OUTPUT_PATH', './dlhd_result.json'), help='Output JSON file path')
    parser.add_argument('--force', action='store_true', help='Force refresh (ignore cache)')
    parser.add_argument('--verbose', action='store_true', help='Verbose logging')
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s [%(levelname)s] %(message)s')

    proxies = parse_proxies(os.environ.get('DLHD_PROXIES', ''))
    headers_env = os.environ.get('DLHD_REQUEST_HEADERS', '{}')
    try:
        extra_headers = json.loads(headers_env)
    except Exception:
        extra_headers = {}

    rc = asyncio.run(run_extraction(args.url, args.output, args.force, proxies, extra_headers))
    sys.exit(rc)

if __name__ == '__main__':
    main()
