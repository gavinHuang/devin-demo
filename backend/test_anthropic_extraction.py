import requests
import json
import trafilatura
from newspaper import Article
from readability import Document
from bs4 import BeautifulSoup

url = 'https://www.anthropic.com/news/tracing-thoughts-language-model'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Referer': 'https://www.google.com/',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Cache-Control': 'max-age=0'
}

try:
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    with open('/tmp/anthropic_raw.html', 'w') as f:
        f.write(response.text)
    
    print(f'Raw HTML saved to /tmp/anthropic_raw.html')
    print(f'Response status: {response.status_code}')
    print(f'Response headers: {json.dumps(dict(response.headers), indent=2)}')
    print(f'First 500 chars of response: {response.text[:500]}')
    
    downloaded = trafilatura.fetch_url(url)
    if downloaded:
        result = trafilatura.extract(downloaded, include_comments=False, 
                                    include_tables=False, 
                                    include_images=False,
                                    include_links=False,
                                    output_format='txt')
        if result and len(result.strip()) > 100:
            metadata = trafilatura.extract_metadata(downloaded)
            title = metadata.title if metadata and metadata.title else "Extracted Content"
            print(f'\nTrafilatura extraction successful:')
            print(f'Title: {title}')
            print(f'Content (first 500 chars): {result[:500]}')
        else:
            print('\nTrafilatura extraction failed or returned insufficient content')
    
    try:
        article = Article(url)
        article.download()
        article.parse()
        
        if article.title and article.text and len(article.text.strip()) > 100:
            print(f'\nNewspaper3k extraction successful:')
            print(f'Title: {article.title}')
            print(f'Content (first 500 chars): {article.text[:500]}')
        else:
            print('\nNewspaper3k extraction failed or returned insufficient content')
    except Exception as e:
        print(f'\nNewspaper3k extraction error: {str(e)}')
    
    try:
        doc = Document(response.text)
        title = doc.title()
        readable_html = doc.summary()
        
        if readable_html:
            soup = BeautifulSoup(readable_html, 'lxml')
            text = soup.get_text(separator='\n\n', strip=True)
            
            if len(text.strip()) > 100:
                print(f'\nReadability extraction successful:')
                print(f'Title: {title}')
                print(f'Content (first 500 chars): {text[:500]}')
            else:
                print('\nReadability extraction failed or returned insufficient content')
        else:
            print('\nReadability extraction failed to generate summary')
    except Exception as e:
        print(f'\nReadability extraction error: {str(e)}')
    
except Exception as e:
    print(f'Error: {str(e)}')
