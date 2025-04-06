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
    Condense text while preserving structure and logical flow.
    Reduces text length to approximately the requested percentage.
    """
    try:
        original_text = request.text
        original_length = len(original_text)
        target_length = int(original_length * (request.percentage / 100))

        paragraphs = re.split(r'\n\s*\n', original_text)

        headings = []
        content_paragraphs = []

        for p in paragraphs:
            p = p.strip()
            if not p:
                continue

            lines = p.split('\n')
            if len(lines) == 1 and len(lines[0]) < 100 and not re.search(r'[.!?]$', lines[0]):
                if request.preserve_headings:
                    headings.append((len(content_paragraphs), p))
                content_paragraphs.append(p)
            else:
                content_paragraphs.append(p)

        if len(content_paragraphs) == 0:
            return TextCondensationResponse(
                original_length=original_length,
                condensed_length=0,
                percentage_achieved=0,
                condensed_text=""
            )

        condensed_paragraphs = []
        current_length = 0

        for i, paragraph in enumerate(content_paragraphs):
            is_heading = any(h[0] == i for h in headings)

            if is_heading and request.preserve_headings:
                condensed_paragraphs.append(paragraph)
                current_length += len(paragraph)
            else:
                paragraph_target = int(len(paragraph) * (request.percentage / 100))

                sentences = re.split(r'(?<=[.!?])\s+', paragraph)

                if len(sentences) <= 2:
                    condensed_paragraphs.append(paragraph)
                    current_length += len(paragraph)
                else:
                    important_sentences = [sentences[0]]

                    key_phrases = ["important", "key", "significant", "essential", "crucial", "critical", "main", "primary"]
                    middle_sentences = sentences[1:-1]

                    scored_sentences = []
                    for idx, sentence in enumerate(middle_sentences):
                        score = 0
                        score += 100 - min(len(sentence), 100)

                        for phrase in key_phrases:
                            if phrase.lower() in sentence.lower():
                                score += 20

                        if re.search(r'\d+', sentence):
                            score += 15

                        scored_sentences.append((idx, sentence, score))

                    scored_sentences.sort(key=lambda x: x[2], reverse=True)

                    current_condensed_length = len(sentences[0])
                    if len(sentences) > 1:
                        current_condensed_length += len(sentences[-1])

                    selected_indices = []
                    for idx, sentence, _ in scored_sentences:
                        if current_condensed_length >= paragraph_target:
                            break
                        selected_indices.append(idx)
                        current_condensed_length += len(sentence)

                    selected_indices.sort()

                    for idx in selected_indices:
                        important_sentences.append(middle_sentences[idx])

                    if len(sentences) > 1:
                        important_sentences.append(sentences[-1])

                    condensed_paragraph = " ".join(important_sentences)
                    condensed_paragraphs.append(condensed_paragraph)
                    current_length += len(condensed_paragraph)

        condensed_text = "\n\n".join(condensed_paragraphs)
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
