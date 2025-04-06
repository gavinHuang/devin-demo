from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg
import requests
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List
import re
import trafilatura
from newspaper import Article
from readability import Document

app = FastAPI()

# Disable CORS. Do not remove this for full-stack development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

class UrlToTextRequest(BaseModel):
    url: HttpUrl = Field(..., description="URL to extract text from")

class UrlToTextResponse(BaseModel):
    title: str
    text: str
    original_url: str

class TextCondensationRequest(BaseModel):
    text: str = Field(..., description="Text to condense")
    percentage: int = Field(50, ge=10, le=90, description="Target percentage of original length (10-90%)")
    preserve_headings: bool = Field(True, description="Whether to preserve headings in the condensed text")

class TextCondensationResponse(BaseModel):
    original_length: int
    condensed_length: int
    percentage_achieved: float
    condensed_text: str

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

@app.post("/api/url-to-text", response_model=UrlToTextResponse)
async def url_to_text(request: UrlToTextRequest):
    """
    Convert URL content to readable text, removing commercial elements and navigation.
    Uses multiple specialized libraries (Trafilatura, Newspaper3k, Readability) for content extraction.
    """
    try:
        url = str(request.url)
        title = "Extracted Content"
        text = ""
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            result = trafilatura.extract(downloaded, include_comments=False, 
                                        include_tables=False, 
                                        include_images=False,
                                        include_links=False,
                                        output_format='txt')
            if result and len(result.strip()) > 100:
                metadata = trafilatura.extract_metadata(downloaded)
                if metadata and metadata.title:
                    title = metadata.title
                text = result
        
        if not text or len(text.strip()) < 100:
            try:
                article = Article(url)
                article.download()
                article.parse()
                
                if article.title:
                    title = article.title
                
                if article.text and len(article.text.strip()) > 100:
                    text = article.text
            except Exception:
                pass
        
        if not text or len(text.strip()) < 100:
            try:
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                
                doc = Document(response.text)
                
                if not title or title == "Extracted Content":
                    title = doc.title()
                
                readable_html = doc.summary()
                if readable_html:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(readable_html, 'lxml')
                    text = soup.get_text(separator='\n\n', strip=True)
            except Exception:
                pass
        
        if text:
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = '\n'.join([line for line in text.split('\n') 
                             if len(line.strip()) > 1 and not re.match(r'^[\d\W]+$', line.strip())])
        else:
            text = "Could not extract readable content from this URL."
        
        return UrlToTextResponse(
            title=title,
            text=text,
            original_url=url
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing URL: {str(e)}")

@app.post("/api/condense-text", response_model=TextCondensationResponse)
async def condense_text(request: TextCondensationRequest):
    """
    Condense text while preserving structure and logical flow using GPT-4o.
    Reduces text length to approximately the requested percentage.
    """
    try:
        import os
        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500, 
                detail="OpenAI API key not found. Please set the OPENAI_API_KEY environment variable."
            )

        client = OpenAI(api_key=api_key)
        
        original_text = request.text
        original_length = len(original_text)
        
        system_prompt = f"""You are an expert in text condensation and summarization. Given an article, your task is to produce a condensed version that maintains the structure and logical flow of the original text while reducing its length to approximately {request.percentage}% of the original.

Instructions:

Preserve the key sections and logical structure of the article, ensuring the output follows the same progression of ideas.

Retain essential details while removing redundancy, filler content, and less critical examples.

Maintain readability and coherence, ensuring smooth transitions between sections.

Do not rephrase excessively—prioritize direct condensation over rewriting.

Formatting:

{"If the input article has headings, keep them in the output." if request.preserve_headings else ""}

Use bullet points or numbered lists if they enhance clarity in the condensed version.
"""

        user_prompt = f"""Input Article:
{original_text}

Condensed Version ({request.percentage}% of Original Length):"""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,  # Lower temperature for more deterministic output
            max_tokens=4000,  # Adjust as needed
        )
        
        condensed_text = response.choices[0].message.content.strip()
        
        condensed_length = len(condensed_text)
        percentage_achieved = (condensed_length / original_length) * 100 if original_length > 0 else 0
        
        return TextCondensationResponse(
            original_length=original_length,
            condensed_length=condensed_length,
            percentage_achieved=percentage_achieved,
            condensed_text=condensed_text
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error condensing text: {str(e)}")
