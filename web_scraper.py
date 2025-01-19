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
import base64
import getpass
from cryptography.fernet import Fernet

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
        self.all_content_file = os.path.join(save_directory, 'all_scraped_content.txt')
        self.config_file = os.path.join(save_directory, '.config')
        
        # 使用固定的密鑰文件
        self.key_file = os.path.join(save_directory, '.key')
        if os.path.exists(self.key_file):
            with open(self.key_file, 'rb') as f:
                self.key = f.read()
        else:
            self.key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(self.key)
        
        self.cipher_suite = Fernet(self.key)
        
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
                print(f"跳過外部鏈接: {url}")
                return False
            
            # 檢查是否是 PDF 文件
            if parsed.path.lower().endswith('.pdf'):
                print(f"跳過 PDF 文件: {url}")
                return False
                
            # 檢查是否是其他文件類型
            if any(parsed.path.lower().endswith(ext) for ext in ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.rar']):
                print(f"跳過文件下載鏈接: {url}")
                return False
            
            # 檢查是否是 Confluence 空間
            if not any(x in parsed.path.lower() for x in ['/display/', '/spaces/']):
                print(f"跳過非文檔頁面: {url}")
                return False
            
            # 排除特殊頁面
            if any(x in parsed.path.lower() for x in [
                'action=edit', 'action=history', 'oldid=', 'diff=', 
                'printable=yes', 'mobileaction=', 'feed=', 'redlink=1',
                '/viewpage.action', 'attachments', 'download'
            ]):
                print(f"跳過特殊頁面: {url}")
                return False
                
            # 排除特殊參數
            if parsed.query and any(x in parsed.query.lower() for x in [
                'view=', 'preview=', 'diff', 'pageId=', 'mode=',
                'download=', 'type=', 'attachment'
            ]):
                print(f"跳過帶特殊參數的頁面: {url}")
                return False
            
            return True
        except:
            print(f"無效的URL: {url}")
            return False

    def extract_links(self, soup, base_url):
        """
        從頁面中提取有效的連結
        """
        links = set()
        all_links = soup.find_all('a', href=True)
        print(f"\n在頁面中找到 {len(all_links)} 個連結")
        
        for link in all_links:
            url = urljoin(base_url, link['href'])
            if self.is_valid_url(url, base_url):
                links.add(url)
        
        print(f"其中有 {len(links)} 個有效連結")
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

    def save_content(self, url, content):
        """
        保存內容到統一的文件中
        """
        try:
            with open(self.all_content_file, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"URL: {url}\n")
                f.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"{'='*80}\n\n")
                f.write(content)
                f.write("\n\n")
            return True
        except Exception as e:
            print(f"保存內容時發生錯誤: {str(e)}")
            return False

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
            self.wait()
            
            # 添加更多的請求頭
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0'
            }
            
            response = self.session.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 移除不需要的元素
            for element in soup.select('script, style, nav, header, footer, .header, .footer, .navigation'):
                element.decompose()
            
            # 特別處理 Confluence 頁面的主要內容
            main_content = soup.select_one('#main-content, .wiki-content') or soup
            
            # 提取標題
            title = soup.select_one('title, h1')
            title_text = title.get_text().strip() if title else ''
            
            # 提取內容
            content = self.clean_text(main_content.get_text())
            
            # 組合完整內容
            full_content = f"標題：{title_text}\n\n{content}" if title_text else content
            
            links = self.extract_links(soup, url)
            
            # 保存內容到統一文件
            self.save_content(url, full_content)
            
            self.visited_urls.add(url)
            return content, links
            
        except Exception as e:
            print(f"爬取頁面時發生錯誤: {str(e)}")
            return None, set()

    def crawl(self, start_url):
        """
        從指定URL開始爬取
        """
        # 檢查是否有之前的進度
        if not self.load_progress(start_url):
            self.visited_urls.clear()
        
        # 使用隊列來實現廣度優先搜索
        queue = deque([(start_url, 0)])  # (url, depth)
        
        try:
            while queue and len(self.visited_urls) < self.max_pages:
                url, depth = queue.popleft()
                
                if url in self.visited_urls:
                    print(f"跳過已訪問的頁面: {url}")
                    continue
                
                print(f"\n正在爬取 (深度 {depth}): {url}")
                content, links = self.scrape_webpage(url, depth)
                
                if content:
                    print(f"成功爬取頁面: {url}")
                else:
                    print(f"無法爬取頁面: {url}")
                
                # 將新的連結加入隊列
                if depth < self.max_depth:
                    new_links = 0
                    for link in links:
                        if link not in self.visited_urls:
                            queue.append((link, depth + 1))
                            new_links += 1
                    print(f"添加了 {new_links} 個新連結到隊列")
                
                # 定期保存進度
                if len(self.visited_urls) % 5 == 0:
                    self.save_progress(start_url)
                    print(f"\n當前進度：已爬取 {len(self.visited_urls)} 個頁面，隊列中還有 {len(queue)} 個頁面")
            
            # 最後保存一次進度
            self.save_progress(start_url)
            print(f"\n爬取完成！共爬取了 {len(self.visited_urls)} 個頁面")
            
        except KeyboardInterrupt:
            print("\n檢測到中斷信號，正在保存進度...")
            self.save_progress(start_url)
            print("進度已保存")
            
        except Exception as e:
            print(f"\n爬取過程中發生錯誤: {str(e)}")
            self.save_progress(start_url)

    def save_credentials(self, username, password):
        """
        保存加密的認證信息
        """
        try:
            encrypted_password = self.cipher_suite.encrypt(password.encode())
            config = {
                'username': username,
                'password': encrypted_password.decode()
            }
            with open(self.config_file, 'w') as f:
                json.dump(config, f)
            print("認證信息已安全保存")
            return True
        except Exception as e:
            print(f"保存認證信息時發生錯誤: {str(e)}")
            return False

    def load_credentials(self):
        """
        讀取加密的認證信息
        """
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                username = config['username']
                encrypted_password = config['password'].encode()
                password = self.cipher_suite.decrypt(encrypted_password).decode()
                return username, password
        except Exception as e:
            print(f"讀取認證信息時發生錯誤: {str(e)}")
        return None, None

def main():
    parser = argparse.ArgumentParser(description='網頁爬蟲工具')
    parser.add_argument('url', help='要爬取的起始URL')
    parser.add_argument('--depth', type=int, default=2, help='最大爬取深度（默認：2）')
    parser.add_argument('--max-pages', type=int, default=50, help='最大爬取頁面數（默認：50）')
    parser.add_argument('--output-dir', default='scraped_content', help='輸出目錄（默認：scraped_content）')
    parser.add_argument('--username', help='認證用戶名')
    parser.add_argument('--password', help='認證密碼')
    parser.add_argument('--min-delay', type=float, default=1, help='最小請求延遲秒數（默認：1）')
    parser.add_argument('--max-delay', type=float, default=3, help='最大請求延遲秒數（默認：3）')
    parser.add_argument('--save-credentials', action='store_true', help='保存認證信息')

    args = parser.parse_args()
    
    scraper = WebScraper(
        args.output_dir,
        max_depth=args.depth,
        max_pages=args.max_pages,
        delay=(args.min_delay, args.max_delay)
    )

    # 處理認證信息
    username = args.username
    password = args.password

    if not (username and password):
        # 嘗試從配置文件加載認證信息
        saved_username, saved_password = scraper.load_credentials()
        if saved_username and saved_password:
            username = saved_username
            password = saved_password
            print(f"使用已保存的認證信息 (用戶名: {username})")
        else:
            try:
                # 如果沒有保存的認證信息，要求用戶輸入
                if not username:
                    username = input("請輸入用戶名: ")
                if not password:
                    password = getpass.getpass("請輸入密碼: ")
            except (EOFError, KeyboardInterrupt):
                print("\n取消輸入，程序結束")
                sys.exit(1)

    # 如果指定了保存認證信息
    if args.save_credentials:
        scraper.save_credentials(username, password)

    # 設置認證
    if username and password:
        scraper.set_auth(username, password)

    try:
        scraper.crawl(args.url)
    except KeyboardInterrupt:
        print("\n檢測到中斷信號，正在結束...")
    except Exception as e:
        print(f"\n發生錯誤: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
