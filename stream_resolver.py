#!/usr/bin/env python3
"""
Stream Resolver - Standalone
Resolves streaming URLs from obfuscated sources
"""

import re
import json
import urllib.parse as urlparse
import string
import random
import requests
from datetime import datetime
import sys

class StreamResolver:
    def __init__(self):
        self.parseDict()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })

    def request(self, url, headers=None, referer=None, cookie=None, post=None, output='content', mobile=False, timeout=15):
        """HTTP request handler"""
        try:
            req_headers = self.session.headers.copy()
            
            if mobile:
                req_headers['User-Agent'] = 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15'
            
            if headers:
                req_headers.update(headers)
            
            if referer:
                req_headers['Referer'] = referer
            
            if cookie:
                req_headers['Cookie'] = cookie
            
            if post:
                response = self.session.post(url, data=post, headers=req_headers, timeout=timeout, allow_redirects=True)
            else:
                response = self.session.get(url, headers=req_headers, timeout=timeout, allow_redirects=True)
            
            if output == 'content':
                return response.text
            elif output == 'geturl':
                return response.url
            elif output == 'cookie':
                return '; '.join([f"{c.name}={c.value}" for c in response.cookies])
            elif output == 'extended':
                return (response.text, response.url, {'Set-Cookie': response.headers.get('Set-Cookie', '')})
            
            return response.text
        except Exception as e:
            print(f"Request error for {url}: {e}")
            return None

    def parseDOM(self, html, element, ret=None, attrs=None):
        """Basic DOM parser"""
        try:
            if attrs:
                pattern = f'<{element}[^>]*'
                for key, value in attrs.items():
                    pattern += f'{key}=["\']?{value}["\']?'
                pattern += '[^>]*'
            else:
                pattern = f'<{element}[^>]*'
            
            if ret:
                pattern += f'{ret}=["\']([^"\']+)["\']'
                matches = re.findall(pattern, html, re.IGNORECASE)
                return matches
            else:
                pattern += '>([^<]+)</'
                matches = re.findall(pattern, html, re.IGNORECASE)
                return matches
        except:
            return []

    def replaceHTMLCodes(self, txt):
        """Decode HTML entities"""
        try:
            import html
            return html.unescape(txt)
        except:
            return txt

    def randomagent(self):
        """Generate random user agent"""
        return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

    def parseIFR(self, url, html):
        """Parse iframe from obfuscated HTML"""
        try:
            # Remove HTML comments
            s = re.compile('(<!--.+?-->)', re.MULTILINE|re.DOTALL).findall(html)
            for i in s: 
                html = html.replace(i, '')

            html = re.sub(r'[^\x00-\x7F]+', ' ', html)
        except:
            pass

        try:
            # Parse concatenated JavaScript variables
            js = re.findall('<script(?: .+?|)>(.+?)</script><script.+?src\s*=\s*\"(.+?)\"(?: .+?|)></script>', html)
            js += re.findall('<script(?: .+?|)>(.+?)</script><script.+?src\s*=\s*\'(.+?)\'(?: .+?|)></script>', html)
            js = [i for i in js if ';' in i[0] and i[1].endswith('.js')]
            js = [(i[0], i[1] if i[1].startswith('http') else urlparse.urljoin(url, i[1])) for i in js]
            js = [(i[0], i[1], self.locParser(i[1])) for i in js]
            js = [i for i in js if i[2] in self.locDict] + [i for i in js if 'id=' in i[0]] + [i for i in js if not i[2] in self.locDict]

            r = self.request(js[0][1])
            r = re.sub(r'[^\x00-\x7F]+', ' ', r)

            var = [re.findall('(.+?)=(.+)', i) for i in re.split('(?:;|,)', js[0][0])]
            var = [i[0] for i in var if i]
            var += re.findall('var\s+(.+?)\s*=\s*(.+?);', r)
            var = [(i[0].replace('\"', '\'').strip(), i[1].replace('\"', '\'').strip()) for i in var]

            r = r.replace(" +", "+").replace("+ ", "+")

            for i in range(100):
                for v in var: 
                    r = r.replace("+%s+" % v[0], "+%s+" % v[1])
                for v in var: 
                    r = r.replace("+%s" % v[0], "+%s" % v[1])
                for v in var: 
                    r = r.replace("%s+'" % v[0], "%s+" % v[1])

            r = r.replace("'+'", "").replace("'+", "").replace("+'", "")

            ifr = self.parseDOM(r, 'iframe', ret='src')[-1]
            ifr = ifr.replace("document.domain", self.locParser(url))
            ifr = ifr if ifr.startswith('http') else urlparse.urljoin(url, ifr)
            ifr = self.replaceHTMLCodes(ifr)

            return ifr
        except:
            pass

        try:
            # Parse script src that are actually URLs
            ifr = self.parseDOM(html, 'script', ret='src', attrs={'type': 'text/javascript'})
            ifr = [i for i in ifr if i.startswith('http') and not i.endswith('.js')]
            ifr = [(self.locParser(i), i) for i in ifr]
            ifr = [i[1] for i in ifr if i[0] in self.locDict][0]
            ifr = self.replaceHTMLCodes(ifr)

            return ifr
        except:
            pass

        try:
            # Standard iframe parsing
            ifr = self.parseDOM(html, 'iframe', ret='src')
            ifr = [(i, re.findall('(http(?:s|)\://.+)', i)) for i in ifr]
            ifr = [i[0] for i in ifr if i[1]]
            ifr = [(i, self.locParser(i)) for i in ifr]
            ifr = [i[0] for i in ifr if i[1] in self.locDict] + [i[0] for i in ifr if not i[1] in self.locDict]
            if not ifr: 
                ifr = self.parseDOM(html, 'iframe.+?', ret='src')
            ifr = [(i, re.findall('(?:\'|\")\s*(\+)', i), re.findall('\s*(\+)(?:\'|\")', i)) for i in ifr]
            ifr = [i[0] for i in ifr if not (i[1] or i[2])]
            ifr = [i if i.startswith('http') else urlparse.urljoin(url, i) for i in ifr]
            ifr = [(i, self.locParser(i)) for i in ifr]
            ifr = [i[0] for i in ifr if not (i[1].startswith('ads.') or '/ads/' in i[0] or '/reclama/' in i[0] or re.findall('(/ad\d+\.php)', i[0]))]
            ifr = ifr[0]
            ifr = self.replaceHTMLCodes(ifr)

            return ifr
        except:
            pass

        try:
            # Meta refresh parsing
            ifr = self.parseDOM(html, 'meta', ret='content')[0]
            ifr = re.findall('url=(http.+)', ifr)[0]
            ifr = self.replaceHTMLCodes(ifr)

            return ifr
        except:
            pass

        try:
            # URL parameter extraction
            ifr = re.findall('^http.+?=(http.+)', url)[0]
            ifr = self.replaceHTMLCodes(ifr)
            return ifr
        except:
            pass

    def parseVAR(self, html):
        """Parse and deobfuscate JavaScript variables"""
        try:
            # Remove HTML comments
            s = re.compile('(<!--.+?-->)', re.MULTILINE|re.DOTALL).findall(html)
            for i in s: 
                html = html.replace(i, '')

            r = html.replace('\n', '#####StreamResolverParseVAR#####')

            r = r.replace(" +", "+").replace("+ ", "+").replace(" ,", ",").replace(", ", ",")

            var = re.findall('var\s+(.+?)\s*=\s*(.+?);', r)
            var = [i for i in var if len(i[0]) > 1]
            
            for i in range(100):
                for v in var: 
                    r = r.replace("+%s+" % v[0], "+%s+" % v[1])
                for v in var: 
                    r = r.replace("+%s" % v[0], "+%s" % v[1])
                for v in var: 
                    r = r.replace("%s+'" % v[0], "%s+" % v[1])

            f = []
            v = re.findall('\"\+(.+?)\+\"', r) + re.findall('\"\+(.+?)\"', r) + re.findall('\"(.+?)\+\"', r) + re.findall('\'\+(.+?)\+\'', r) + re.findall('\'\+(.+?)\'', r) + re.findall('\'(.+?)\+\'', r)
            v = [i.strip() for i in v if not ('+' in i or "'" in i or '"' in i)]
            fun = re.findall('function (.+?)\s*\(', r)
            
            for a in fun:
                b = list(zip(re.findall('function\s+%s\s*\((.+?)\)' % a, r), re.findall('<script>\s*%s\((.+?)\)' % a, r)))
                for c in b:
                    d = list(zip(c[0].split(','), c[1].split(',')))
                    f += d
            
            var = [i for i in f if i[0].strip() in v]
            
            for i in range(100):
                for v in var: 
                    r = r.replace("+%s+" % v[0], "+%s+" % v[1])
                for v in var: 
                    r = r.replace("+%s" % v[0], "+%s" % v[1])
                for v in var: 
                    r = r.replace("%s+'" % v[0], "%s+" % v[1])

            r = r.replace("'+'", "").replace("\"+\"", "").replace("\"+'", "").replace("'+\"", "")
            r = r.replace("'+", "").replace("+'", "").replace("\"+", "").replace("+\"", "")

            var = re.findall('(\[.+?\]\.join\(\"\"\))', r)
            for v in var:
                r = r.replace(v, v.replace('.join("")', '').replace('"', '').replace(',', '').replace('[', '').replace(']', ''))

            var = re.findall('document\.getElementById\("(.+?)"\)\.innerHTML', r)
            for v in var:
                i = re.findall('=%s>(.+?)<' % v, r)
                if i: 
                    r = r.replace('+document.getElementById("%s").innerHTML' % v, i[0])

            var = re.compile('(function\s+.+?\(\) \{.+?return\s*\(.+?\);)', re.MULTILINE|re.DOTALL).findall(r)
            for v in var:
                r = r.replace(v, '')
                i = re.compile('function\s+(.+?\(\))\s+\{.+?return\s*\((.+?)\)', re.MULTILINE|re.DOTALL).findall(v)
                if i: 
                    r = r.replace(i[0][0], '+\'%s\'+' % i[0][1])
            
            var = re.findall('(\'\+.+?\+\')', r)
            for v in var:
                r = r.replace(v, v.replace("'+", "").replace("+'", ""))
            
            r = r.replace('\\', '')

            r = r.replace('#####StreamResolverParseVAR#####', '\n')
            return r
        except:
            return html

    def parseWS(self, html):
        """Parse Wise obfuscation"""
        def wsexec(s):
            try: 
                parts = s.split(',')
                return self.__unwise(
                    parts[0].strip('\''), 
                    parts[1].strip('\''), 
                    parts[2].strip('\''), 
                    parts[3].strip('\'')
                )
            except: 
                return None
        
        if 'function(w,i,s,e)' not in html: 
            return html
        
        ws = re.compile("}[(]('.+?' *, *'.+?' *, *'.+?' *, *'.+?')[)]").findall(html)
        for i in ws: 
            try: 
                result = wsexec(i)
                if result:
                    html += str(result)
            except: 
                pass
        
        return html

    def __unwise(self, w, i, s, e):
        """Unwise deobfuscation implementation"""
        lIll = 0
        ll1I = 0
        Il1l = 0
        ll1l = []
        l1lI = []
        
        while True:
            if (lIll < 5): 
                l1lI.append(w[lIll])
            elif (lIll < len(w)): 
                ll1l.append(w[lIll])
            lIll += 1
            
            if (ll1I < 5): 
                l1lI.append(i[ll1I])
            elif (ll1I < len(i)): 
                ll1l.append(i[ll1I])
            ll1I += 1
            
            if (Il1l < 5): 
                l1lI.append(s[Il1l])
            elif (Il1l < len(s)): 
                ll1l.append(s[Il1l])
            Il1l += 1
            
            if (len(w) + len(i) + len(s) + len(e) == len(ll1l) + len(l1lI) + len(e)): 
                break
        
        lI1l = ''.join(ll1l)
        I1lI = ''.join(l1lI)
        ll1I = 0
        l1ll = []
        
        for lIll in range(0, len(ll1l), 2):
            ll11 = -1
            ll11 = 1 if (ord(I1lI[ll1I]) % 2) else ll11
            l1ll.append(chr(int(lI1l[lIll: lIll+2], 36) - ll11))
            ll1I += 1
            ll1I = 0 if (ll1I >= len(l1lI)) else ll1I
        
        ret = ''.join(l1ll)
        
        if 'eval(function(w,i,s,e)' in ret: 
            match = re.compile('eval\(function\(w,i,s,e\).*}\((.*?)\)').findall(ret)
            if match:
                return wsexec(match[0])
        else: 
            return ret

    def locParser(self, url):
        """Extract domain from URL"""
        try:
            url = url.strip().lower()
            url = urlparse.urlparse(url).netloc
            url = re.sub('^www\.|^www\d+\.|^cdn\.|^emb\.|^emb.+?\.', '', url)
            return url
        except:
            return url

    def findParser(self, html, url):
        """Find specific parameter in HTML"""
        try: 
            return re.findall('(?:\'|\")%s(?:\'|\")\s*:\s*(?:\'|\")(.+?)(?:\'|\")' % url, html)[0]
        except: 
            pass
        try: 
            return re.findall('%s\s*=\s*(?:\'|\")(.+?)(?:\'|\")' % url, html)[0]
        except: 
            pass
        try: 
            return re.findall('%s\s*:\s*(?:\'|\")(.+?)(?:\'|\")' % url, html)[0]
        except: 
            pass

    def parseDict(self):
        """Initialize known streaming domains"""
        self.locinfoDict = [{
            'name': 'hls',
            'netloc': ['streamtpmedia.com', 'aliez.tv', 'aliez.me', 'b-c-e.us', 'bcast.pw', 'bcast.site', 
                      'bro.adca.st', 'cast4u.tv', 'castfree.me', 'cndhlsstream.pw', 'megadash.xyz', 
                      'gibanica.club', 'janjuaplayer.com', 'jazztv.co', 'mybeststream.xyz', 'live247.online', 
                      'livesport.pw', 'livestream.com', 'livetv.ninja', 'lshstreams.com', 'nowlive.club', 
                      'nowlive.pw', 'nowlive.xyz', 'miplayer.net', 'onhockey.tv', 'p3g.tv', 'playlive.pw', 
                      'potvod.com', 'rocktv.co', 'scity.tv', 'skstream.tv', 'sportsvideoline3.pw', 
                      'streamm.eu', 'theactionlive.com', 'webtv.ws', 'widestream.io']
        }]

        self.locDict = sum([i['netloc'] for i in self.locinfoDict], [])

    def hls(self, url, ref):
        """Main HLS resolver"""
        try:
            l = self.locParser(url)

            a = self.randomagent()
            h = {'User-agent': a}

            r = self.request(url, referer=ref)
            
            if r is None:
                return None
            
            r = self.parseWS(r)
            r = self.parseVAR(r)

            # Extract all quoted strings
            s = re.findall('\'(.+?)\'', r) + re.findall('\"(.+?)\"', r) + \
                re.findall('\'(http.+?)\'', r) + re.findall('\"(http.+?)\"', r)

            # Try base64 decoding
            s2 = []
            for i in s:
                try: 
                    if i.startswith('http'): 
                        raise Exception()
                    import base64
                    decoded = base64.b64decode(i).decode('utf-8')
                    s2.append(decoded)
                except:
                    pass
            s += s2

            # URL decode
            s = [urlparse.unquote(i) for i in s]

            # Find m3u8 URLs
            u = [i for i in s if i.startswith('http') and '.m3u8' in i]

            if not u:
                # Try to find RTMP URLs as fallback
                u = re.findall('\'(rtmp.+?)\'', r) + re.findall('\"(rtmp.+?)\"', r)
                if u:
                    return u[0]
                return None

            u = u[0]

            h = {
                'User-agent': a, 
                'Referer': url, 
                'X-Requested-With': 'ShockwaveFlash/21.0.0.242'
            }

            # Try to get the actual stream URL
            try:
                x = self.request(u, headers=h)
                if x:
                    y = [i for i in x.splitlines() if '.m3u8' in i]
                    if y:
                        u = urlparse.urljoin(u, y[0])
                        x = self.request(u, headers=h)
                    
                    if x and '#EXTINF' not in x:
                        return None
                
                u = self.request(u, headers=h, output='geturl')
            except:
                pass

            # Format with headers
            r = '|%s' % urlparse.urlencode(h)
            u += r
            
            return u
        except Exception as e:
            print(f"HLS resolver error: {e}")
            return None

    def redirect(self, url, ref=None, limit=5):
        """Follow redirect chain"""
        if self.locParser(url) in self.locDict: 
            return (url, ref)

        for i in range(0, limit):
            try:
                url = self.request(url, referer=ref, output='geturl')

                r = self.request(url, headers={'Host': self.locParser(url)}, referer=ref)
                if r is None: 
                    r = self.request(url, referer=ref)
                if r is None: 
                    raise Exception()

                r = self.parseIFR(url, r)
                if r is None: 
                    raise Exception()

                ref = url
                url = r
                
                if self.locParser(url) in self.locDict:
                    return (url, ref)
            except:
                break
        
        return (url, ref)

    def resolve(self, url, ref=None):
        """Main resolve method"""
        try:
            if ref is None:
                try: 
                    url, ref = re.findall('(.+?)\|Referer=(.+)', url)[0]
                except: 
                    ref = None

            try: 
                a = [i['name'] for i in self.locinfoDict if self.locParser(url) in i['netloc']][0]
            except: 
                a = 'hls'
            
            url = getattr(self, a)(url, ref)

            return url
        except Exception as e:
            print(f"Resolve error: {e}")
            return None


def main():
    """Main function"""
    urls = [
        'https://streamtpmedia.com/global1.php?stream=espn',
        'https://streamtpmedia.com/global1.php?stream=espndeportes'
    ]
    
    # Allow custom URLs from command line
    if len(sys.argv) > 1:
        urls = sys.argv[1:]
    
    resolver = StreamResolver()
    results = {
        'timestamp': datetime.now().isoformat(),
        'streams': []
    }
    
    for url in urls:
        print(f"\n{'='*60}")
        print(f"Processing: {url}")
        print(f"{'='*60}")
        
        try:
            # Follow redirects first
            resolved_url, referer = resolver.redirect(url)
            print(f"After redirect: {resolved_url}")
            
            # Resolve the stream
            stream_url = resolver.resolve(resolved_url, referer)
            
            if stream_url:
                print(f"✓ Stream resolved successfully")
                
                # Parse the URL and headers
                if '|' in stream_url:
                    clean_url, headers_str = stream_url.split('|', 1)
                    headers = dict(urlparse.parse_qsl(headers_str))
                else:
                    clean_url = stream_url
                    headers = {}
                
                results['streams'].append({
                    'input_url': url,
                    'resolved_url': resolved_url,
                    'stream_url': clean_url,
                    'headers': headers,
                    'referer': referer,
                    'status': 'success'
                })
                
                print(f"Stream URL: {clean_url}")
                if headers:
                    print(f"Headers: {json.dumps(headers, indent=2)}")
            else:
                print(f"✗ Failed to resolve stream")
                results['streams'].append({
                    'input_url': url,
                    'status': 'failed',
                    'error': 'Could not extract stream URL'
                })
        
        except Exception as e:
            print(f"✗ Error: {e}")
            results['streams'].append({
                'input_url': url,
                'status': 'error',
                'error': str(e)
            })
    
    # Save results
    output_file = 'resolved_streams.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"Results saved to {output_file}")
    print(f"{'='*60}")
    print(json.dumps(results, indent=2))
    
    return 0 if all(s['status'] == 'success' for s in results['streams']) else 1


if __name__ == "__main__":
    sys.exit(main())
