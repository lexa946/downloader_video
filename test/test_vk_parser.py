import asyncio
import aiohttp
import ssl
import re
import aiofiles
import json
from pathlib import Path
from urllib.parse import urlencode

async def get_vk_video(url: str, output_path: str):
    owner_id, video_id = re.search(r"video(\d+_\d+)", url).group(1).split("_")
    print(f"Video ID: {owner_id}_{video_id}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 YaBrowser/25.6.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1"
    }

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    async with aiohttp.ClientSession(headers=headers) as session:
        # First, get the video page to extract hash
        print(f"Getting video page: {url}")
        
        async with session.get(url, ssl=ssl_context) as response:
            html = await response.text()
            
            # Save video page
            async with aiofiles.open("output/video_page.html", "w", encoding="utf-8") as f:
                await f.write(html)
            
            # Extract hash from og:video meta tag
            hash_match = re.search(r'og:video" content="[^"]*hash=([^&"]+)', html)
            if hash_match:
                video_hash = hash_match.group(1)
                print(f"Found video hash: {video_hash}")
            else:
                print("No hash found, trying without hash")
                video_hash = None
        
        # Get embed page with hash
        if video_hash:
            embed_url = f"https://vk.com/video_ext.php?oid={owner_id}&id={video_id}&hash={video_hash}"
        else:
            embed_url = f"https://vk.com/video_ext.php?oid={owner_id}&id={video_id}"
        
        print(f"Getting embed page: {embed_url}")
        
        headers.update({
            "Referer": url,
            "Origin": "https://vk.com"
        })
        
        async with session.get(embed_url, headers=headers, ssl=ssl_context) as response:
            html = await response.text()
            
            # Save embed page
            async with aiofiles.open("output/embed_page.html", "w", encoding="utf-8") as f:
                await f.write(html)
            
            print(f"Embed response status: {response.status}")
            print(f"Embed response length: {len(html)}")
            
            # Extract video URLs from embed page
            video_urls = {}
            
            # Find HLS URL
            hls_match = re.search(r'"hls":"([^"]+)"', html)
            if hls_match:
                video_urls['hls'] = hls_match.group(1).replace('\\/', '/')
                print(f"Found HLS URL: {video_urls['hls']}")
            
            # Find DASH URL
            dash_match = re.search(r'"dash_sep":"([^"]+)"', html)
            if dash_match:
                video_urls['dash'] = dash_match.group(1).replace('\\/', '/')
                print(f"Found DASH URL: {video_urls['dash']}")
            
            # Find direct video URLs
            for quality in ['144', '240', '360', '480']:
                url_match = re.search(f'"url{quality}":"([^"]+)"', html)
                if url_match:
                    video_urls[f'url{quality}'] = url_match.group(1).replace('\\/', '/')
                    print(f"Found {quality}p URL: {video_urls[f'url{quality}']}")
            
            # Also try to find URLs in JavaScript
            js_urls = re.findall(r'url["\']?\s*:\s*["\']([^"\']+)["\']', html)
            if js_urls:
                print(f"Found URLs in JavaScript: {js_urls[:5]}")
            
            if not video_urls:
                print("No video URLs found!")
                return
            
            # Download the highest quality available
            preferred_qualities = ['url480', 'url360', 'url240', 'url144', 'hls', 'dash']
            download_url = None
            quality_name = None
            
            for quality in preferred_qualities:
                if quality in video_urls:
                    download_url = video_urls[quality]
                    quality_name = quality
                    break
            
            if not download_url:
                print("No suitable video URL found!")
                return
            
            print(f"Downloading video with quality: {quality_name}")
            print(f"URL: {download_url}")
            
            # Download video
            try:
                async with session.get(download_url, ssl=ssl_context) as video_response:
                    if video_response.status == 200:
                        # Determine file extension
                        if quality_name == 'hls':
                            ext = '.m3u8'
                        elif quality_name == 'dash':
                            ext = '.mpd'
                        else:
                            ext = '.mp4'
                        
                        filename = f"output/video_{owner_id}_{video_id}_{quality_name}{ext}"
                        
                        async with aiofiles.open(filename, "wb") as f:
                            async for chunk in video_response.content.iter_chunked(8192):
                                await f.write(chunk)
                        
                        print(f"Video downloaded successfully: {filename}")
                        
                        # If it's HLS, also download the m3u8 file content
                        if quality_name == 'hls':
                            m3u8_content = await video_response.text()
                            async with aiofiles.open(f"output/video_{owner_id}_{video_id}_hls_content.m3u8", "w") as f:
                                await f.write(m3u8_content)
                            print(f"HLS content saved: output/video_{owner_id}_{video_id}_hls_content.m3u8")
                    else:
                        print(f"Failed to download video: {video_response.status}")
            except Exception as e:
                print(f"Error downloading video: {e}")

async def main():
    url = "https://vk.com/video335482664_456239334"
    await get_vk_video(url, "output")

if __name__ == "__main__":
    asyncio.run(main())