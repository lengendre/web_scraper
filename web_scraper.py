import requests
from bs4 import BeautifulSoup
import os
import time
from urllib.parse import urlparse, urljoin
import sys
import argparse
from collections import deque
import re
import json
import random

# 設定控制台輸出編碼為UTF-8
sys.stdout.reconfigure(encoding='utf-8')

class WebScraper:
    def __init__(self, save_directory, max_depth=2, max_pages=50, delay=(1, 3)):
        """
        初始化爬蟲類
        :param save_directory: 儲存內容的目錄路徑
        :param max_depth: 最大爬取深度
        :param max_pages: 最大爬取頁面數
        :param delay: 請求延遲範圍（最小值，最大值）秒
        """
        self.save_directory = save_directory
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.delay = delay
        self.visited_urls = set()
        self.session = requests.Session()
        self.session.verify = False
        
        # 創建必要的目錄
        if not os.path.exists(save_directory):
            os.makedirs(save_directory)
        
        # 創建進度保存目錄
        self.progress_dir = os.path.join(save_directory, '_progress')
        if not os.path.exists(self.progress_dir):
            os.makedirs(self.progress_dir)

    def set_auth(self, username, password):
        """
        設置基本認證
        """
        self.session.auth = (username, password)

    def load_progress(self, start_url):
        """
        加載之前的爬取進度
        """
        progress_file = os.path.join(self.progress_dir, 'progress.json')
        if os.path.exists(progress_file):
            try:
                with open(progress_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('start_url') == start_url:
                        self.visited_urls = set(data.get('visited_urls', []))
                        print(f"已加載之前的進度，已爬取 {len(self.visited_urls)} 個頁面")
                        return True
            except Exception as e:
                print(f"加載進度時發生錯誤: {str(e)}")
        return False

    def save_progress(self, start_url):
        """
        保存爬取進度
        """
        progress_file = os.path.join(self.progress_dir, 'progress.json')
        try:
            data = {
                'start_url': start_url,
                'visited_urls': list(self.visited_urls),
                'timestamp': time.time()
            }
            with open(progress_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存進度時發生錯誤: {str(e)}")
            return False

    def is_valid_url(self, url, base_url):
        """
        檢查URL是否有效且在目標範圍內
        """
        try:
            parsed = urlparse(url)
            base_parsed = urlparse(base_url)
            
            # 檢查域名
            if parsed.netloc != base_parsed.netloc:
                return False
            
            # 檢查路徑是否在同一目錄下
            base_path = os.path.dirname(base_parsed.path)
            if not parsed.path.startswith(base_path):
                return False
            
            # 排除特殊頁面
            if any(x in parsed.path.lower() for x in [
                'action=edit', 'action=history', 'oldid=', 'diff=', 
                'printable=yes', 'mobileaction=', 'feed=', 'redlink=1'
            ]):
                return False
            
            return True
        except:
            return False

    def extract_links(self, soup, base_url):
        """
        從頁面中提取有效的連結
        """
        links = set()
        for link in soup.find_all('a', href=True):
            url = urljoin(base_url, link['href'])
            if self.is_valid_url(url, base_url):
                links.add(url)
        return links

    def clean_text(self, text):
        """
        清理文字內容
        """
        # 移除多餘的空白
        text = ' '.join(text.split())
        # 移除特殊控制字符
        text = ''.join(char for char in text if ord(char) >= 32 or char == '\n')
        return text

    def wait(self):
        """
        根據設定的延遲範圍等待
        """
        time.sleep(random.uniform(self.delay[0], self.delay[1]))

    def scrape_webpage(self, url, depth=0):
        """
        爬取指定網頁的內容
        :param url: 要爬取的網頁URL
        :param depth: 當前爬取深度
        :return: (內容, 連結集合)
        """
        if url in self.visited_urls:
            return None, set()
        
        if depth > self.max_depth or len(self.visited_urls) >= self.max_pages:
            return None, set()

        try:
            print(f"正在爬取 (深度 {depth}): {url}")
            
            # 添加延遲
            self.wait()
            
            # 添加 User-Agent
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # 發送請求
            response = self.session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            # 解析HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 移除不需要的元素
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                element.decompose()
            
            # 獲取純文字內容
            text_content = []
            for element in soup.stripped_strings:
                text = self.clean_text(element)
                if text and len(text) > 1:
                    text_content.append(text)
            
            content = '\n\n'.join(text_content)
            
            # 提取連結
            links = self.extract_links(soup, url)
            
            # 標記為已訪問
            self.visited_urls.add(url)
            
            return content, links
            
        except Exception as e:
            print(f"爬取過程中發生錯誤: {str(e)}")
            return None, set()

    def save_content(self, content, url):
        """
        將爬取到的內容保存到文件
        """
        if content:
            parsed = urlparse(url)
            base_name = parsed.netloc.replace('.', '_')
            path_name = parsed.path.replace('/', '_')
            if not path_name:
                path_name = 'index'
            
            filename = f"{base_name}{path_name}_{int(time.time())}.txt"
            file_path = os.path.join(self.save_directory, filename)
            
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"URL: {url}\n\n")
                    f.write(content)
                print(f"內容已保存到: {file_path}")
                return True
            except Exception as e:
                print(f"保存內容時發生錯誤: {str(e)}")
        return False

    def crawl(self, start_url):
        """
        從指定URL開始爬取
        """
        # 嘗試加載之前的進度
        self.load_progress(start_url)
        
        queue = deque([(start_url, 0)])  # (url, depth)
        last_save_time = time.time()
        
        try:
            while queue and len(self.visited_urls) < self.max_pages:
                url, depth = queue.popleft()
                
                if url in self.visited_urls:
                    continue
                    
                content, links = self.scrape_webpage(url, depth)
                if content:
                    self.save_content(content, url)
                    
                # 將新的連結加入隊列
                if depth < self.max_depth:
                    for link in links:
                        if link not in self.visited_urls:
                            queue.append((link, depth + 1))
                
                # 每爬取10個頁面或經過5分鐘就保存一次進度
                if len(self.visited_urls) % 10 == 0 or time.time() - last_save_time > 300:
                    self.save_progress(start_url)
                    last_save_time = time.time()
                
                # 顯示進度
                print(f"已爬取 {len(self.visited_urls)} 個頁面，隊列中還有 {len(queue)} 個頁面待爬取")
        
        except KeyboardInterrupt:
            print("\n檢測到中斷信號，正在保存進度...")
            self.save_progress(start_url)
            print("進度已保存，可以使用相同的參數重新運行程序來繼續爬取")
            sys.exit(0)
        
        # 完成時保存最終進度
        self.save_progress(start_url)

def main():
    parser = argparse.ArgumentParser(description='網頁爬蟲工具')
    parser.add_argument('url', help='要爬取的網頁URL')
    parser.add_argument('--depth', type=int, default=2, help='最大爬取深度')
    parser.add_argument('--max-pages', type=int, default=50, help='最大爬取頁面數')
    parser.add_argument('--output-dir', default='scraped_content', help='輸出目錄')
    parser.add_argument('--username', help='基本認證用戶名')
    parser.add_argument('--password', help='基本認證密碼')
    parser.add_argument('--min-delay', type=float, default=1.0, help='最小請求延遲（秒）')
    parser.add_argument('--max-delay', type=float, default=3.0, help='最大請求延遲（秒）')
    
    args = parser.parse_args()
    
    scraper = WebScraper(
        args.output_dir, 
        args.depth, 
        args.max_pages,
        delay=(args.min_delay, args.max_delay)
    )
    
    if args.username and args.password:
        scraper.set_auth(args.username, args.password)
    
    scraper.crawl(args.url)

if __name__ == "__main__":
    main()
