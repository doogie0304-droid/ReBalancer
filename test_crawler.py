from crawler import NaverETFCrawler
from bs4 import BeautifulSoup

c = NaverETFCrawler()
html = c.fetch_page('379800', 1)

soup = BeautifulSoup(html, 'html.parser')
tables = soup.find_all('table')
print(f"테이블 수: {len(tables)}")
if tables:
    print(f"첫 테이블 class: {tables[0].get('class')}")