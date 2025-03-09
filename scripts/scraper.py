from fastapi import FastAPI
from pydantic import BaseModel
import os, openai, requests, smtplib
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from email.mime.text import MIMEText

load_dotenv()

app = FastAPI()

class ScrapeRequest(BaseModel):
    query: str
    num_articles: int
    email: str

@app.post("/api/sendDigest")
async def scrape(req: ScrapeRequest):
    articles = scrape_articles(req.query, req.num_articles)
    summaries = [summarize(a["content"]) for a in articles if a["content"].strip()]
    send_email_digest(req.email, summaries)
    return {"status": "digest sent"}

def scrape_articles(query, num_articles):
    url = f'https://www.bing.com/news/search?q={query}'
    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')

    articles = []
    cards = soup.select('a.title')[:num_articles]

    for h in cards:
        title = h.get_text(strip=True)
        link = h['href']
        if not link.startswith("http"):
            link = "https://www.bing.com" + link

        content_res = requests.get(link)
        content_soup = BeautifulSoup(content_res.text, "html.parser")
        paragraphs = content_soup.find_all('p')
        content = ' '.join([p.get_text() for p in paragraphs if p.get_text(strip=True)])

        articles.append({"title": title, "content": content})
    return articles

import requests
import os

HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")

def summarize(text):
    API_URL = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"
    headers = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}

    payload = {
        "inputs": text[:1024],  # Keep text within token limits
        "parameters": {"max_length": 150, "min_length": 50, "do_sample": False},
    }

    response = requests.post(API_URL, headers=headers, json=payload)

    if response.status_code == 200:
        return response.json()[0]["summary_text"]
    else:
        print("Error:", response.json())
        return "Summarization failed."

def send_email_digest(email, summaries):
    import smtplib
    ORIGIN_EMAIL = os.getenv("ORIGIN_EMAIL")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

    from email.mime.text import MIMEText

    email_body = "\n\n".join(summaries) if summaries else "No summaries available."

    msg = MIMEText(email_body)
    msg['Subject'] = 'Your daily news digest'
    msg['From'] = ORIGIN_EMAIL
    msg['To'] = email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(ORIGIN_EMAIL, EMAIL_PASSWORD)
        server.sendmail(ORIGIN_EMAIL, email, msg.as_string())
