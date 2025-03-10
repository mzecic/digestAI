from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os, requests, smtplib, traceback, json, feedparser
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi.middleware.cors import CORSMiddleware
import logging
from datetime import datetime, timedelta
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("digest-api")

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class NewsRequest(BaseModel):
    query: str
    email: str
    num_articles: int = 5

@app.post("/api/sendDigest")
async def send_digest(req: NewsRequest):
    try:
        logger.info(f"➡️ Received request: {req.model_dump()}")

        # Step 1: Get quality news articles
        logger.info(f"Searching for news about: {req.query}")
        articles = get_quality_news(req.query, req.num_articles)
        logger.info(f"Found {len(articles)} articles")

        if not articles:
            return {"status": "no articles found", "query": req.query}

        # Step 2: Generate summaries
        logger.info("Generating summaries...")
        for article in articles:
            if article.get("content") and not article.get("summary"):
                article["summary"] = summarize(article["content"])

        # Step 3: Send email with articles and summaries
        logger.info(f"Sending email to {req.email} with {len(articles)} articles")
        send_email_digest(req.email, articles)
        logger.info("Email sent successfully")

        return {
            "status": "digest sent",
            "article_count": len(articles),
            "articles": [{"title": a["title"], "source": a.get("source", "Unknown")} for a in articles]
        }

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        logger.error(traceback.format_exc())
        return {"status": "error", "message": str(e)}

def get_quality_news(query, num_articles):
    """Get high-quality news articles using multiple sources"""
    articles = []

    # Try NewsAPI first (most reliable if you have an API key)
    if os.getenv("NEWSAPI_KEY"):
        try:
            articles = get_news_from_newsapi(query, num_articles)
            if len(articles) >= num_articles:
                return articles[:num_articles]
        except Exception as e:
            logger.error(f"Error with NewsAPI: {e}")

    # Try RSS feeds next (more reliable than direct scraping)
    if len(articles) < num_articles:
        try:
            rss_articles = get_news_from_rss(query, num_articles - len(articles))
            articles.extend(rss_articles)
            if len(articles) >= num_articles:
                return articles[:num_articles]
        except Exception as e:
            logger.error(f"Error with RSS feeds: {e}")

    # Try Google News for anything remaining (more reliable than Bing)
    if len(articles) < num_articles:
        try:
            google_articles = get_news_from_google(query, num_articles - len(articles))
            articles.extend(google_articles)
            if len(articles) >= num_articles:
                return articles[:num_articles]
        except Exception as e:
            logger.error(f"Error with Google News: {e}")

    # Last resort, try Bing News
    if len(articles) < num_articles:
        try:
            bing_articles = get_news_from_bing(query, num_articles - len(articles))
            articles.extend(bing_articles)
        except Exception as e:
            logger.error(f"Error with Bing News: {e}")

    # If we still have nothing, generate a fallback article
    if not articles:
        articles.append({
            "title": f"News about {query}",
            "source": "DigestAI",
            "url": f"https://news.google.com/search?q={query}",
            "publishedAt": datetime.now().isoformat(),
            "summary": f"We couldn't retrieve specific news articles about '{query}'. Try visiting a news site directly to search for this topic."
        })

    # Deduplicate articles based on title similarity
    unique_articles = []
    seen_titles = set()

    for article in articles:
        # Normalize title to check for duplicates
        norm_title = normalize_title(article["title"])

        if norm_title not in seen_titles:
            seen_titles.add(norm_title)
            unique_articles.append(article)

    return unique_articles[:num_articles]

def normalize_title(title):
    """Normalize title for deduplication"""
    # Convert to lowercase, remove punctuation, and split into words
    words = re.findall(r'\w+', title.lower())
    # Keep only significant words (longer than 3 chars)
    significant = [w for w in words if len(w) > 3]
    # Sort to make word order irrelevant
    return " ".join(sorted(significant))

def get_news_from_newsapi(query, num_articles):
    """Get news from NewsAPI.org (requires API key)"""
    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key:
        logger.warning("No NewsAPI key found")
        return []

    logger.info("Fetching news from NewsAPI.org")
    url = f"https://newsapi.org/v2/everything?q={query}&language=en&sortBy=publishedAt&pageSize={num_articles}"
    headers = {"X-Api-Key": api_key}

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        logger.error(f"NewsAPI error: {response.status_code}, {response.text}")
        return []

    data = response.json()
    articles = []

    for item in data.get("articles", []):
        articles.append({
            "title": item.get("title", "Untitled"),
            "source": item.get("source", {}).get("name", "Unknown"),
            "url": item.get("url", ""),
            "publishedAt": item.get("publishedAt", ""),
            "content": item.get("content", item.get("description", "")),
            "summary": item.get("description", "")
        })

    logger.info(f"Found {len(articles)} articles from NewsAPI")
    return articles

def get_news_from_rss(query, num_articles):
    """Get news from popular RSS feeds"""
    logger.info("Fetching news from RSS feeds")

    # List of popular news RSS feeds
    rss_feeds = [
        "http://rss.cnn.com/rss/cnn_topstories.rss",
        "https://moxie.foxnews.com/feedburner/latest.xml",
        "http://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.npr.org/rss/rss.php?id=1001",
        "http://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"
    ]

    articles = []
    query_terms = set(query.lower().split())

    for feed_url in rss_feeds:
        try:
            logger.debug(f"Parsing RSS feed: {feed_url}")
            feed = feedparser.parse(feed_url)

            for entry in feed.entries:
                # Check if article is relevant to the query
                title = entry.get("title", "").lower()
                summary = entry.get("summary", "").lower()

                # Check if any query term is in the title or summary
                is_relevant = any(term in title or term in summary for term in query_terms)

                if is_relevant:
                    articles.append({
                        "title": entry.get("title", "Untitled"),
                        "source": feed.feed.get("title", "RSS Feed"),
                        "url": entry.get("link", ""),
                        "publishedAt": entry.get("published", ""),
                        "content": entry.get("summary", ""),
                        "summary": entry.get("summary", "")
                    })

                if len(articles) >= num_articles:
                    break

            if len(articles) >= num_articles:
                break

        except Exception as e:
            logger.error(f"Error parsing RSS feed {feed_url}: {e}")

    logger.info(f"Found {len(articles)} articles from RSS feeds")
    return articles

def get_news_from_google(query, num_articles):
    """Get news from Google News"""
    logger.info("Fetching news from Google News")

    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

    try:
        feed = feedparser.parse(url)
        articles = []

        for entry in feed.entries[:num_articles]:
            # Extract source from title (Google News format: "Title - Source")
            title_parts = entry.title.split(" - ")
            source = title_parts[-1] if len(title_parts) > 1 else "Google News"
            title = " - ".join(title_parts[:-1]) if len(title_parts) > 1 else entry.title

            articles.append({
                "title": title,
                "source": source,
                "url": entry.link,
                "publishedAt": entry.get("published", ""),
                "content": entry.get("summary", ""),
                "summary": entry.get("summary", "")
            })

        logger.info(f"Found {len(articles)} articles from Google News")
        return articles

    except Exception as e:
        logger.error(f"Error with Google News: {e}")
        return []

def get_news_from_bing(query, num_articles):
    """Get news from Bing News (fallback method)"""
    logger.info("Fetching news from Bing News")

    url = f'https://www.bing.com/news/search?q={query}&format=rss'

    try:
        feed = feedparser.parse(url)
        articles = []

        for entry in feed.entries[:num_articles]:
            articles.append({
                "title": entry.get("title", "Untitled"),
                "source": "Bing News",
                "url": entry.get("link", ""),
                "publishedAt": entry.get("published", ""),
                "content": entry.get("summary", ""),
                "summary": entry.get("summary", "")
            })

        logger.info(f"Found {len(articles)} articles from Bing News")
        return articles

    except Exception as e:
        logger.error(f"Error with Bing News: {e}")
        return []

def summarize(text):
    """Generate a summary of the article text"""
    HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")

    if not HUGGINGFACE_API_KEY:
        logger.warning("No HUGGINGFACE_API_KEY found, using fallback summarizer")
        return fallback_summarize(text)

    # If text is too short, don't bother summarizing
    if len(text) < 300:
        return text

    try:
        logger.debug("Calling Hugging Face API for summarization")
        API_URL = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"
        headers = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}

        payload = {
            "inputs": text[:1024],  # Keep text within token limits
            "parameters": {"max_length": 150, "min_length": 50, "do_sample": False},
        }

        response = requests.post(API_URL, headers=headers, json=payload)

        if response.status_code == 200:
            summary = response.json()[0]["summary_text"]
            return summary
        else:
            logger.error(f"Summarization API error: {response.status_code}, {response.text}")
            return fallback_summarize(text)
    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        return fallback_summarize(text)

def fallback_summarize(text):
    """Simple fallback summarizer that extracts key sentences"""
    logger.debug("Using fallback summarizer")

    # If text is short enough, just return it
    if len(text) < 300:
        return text

    # Split text into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) <= 3:
        return text

    # For longer text, take first two sentences and last sentence
    summary = ' '.join(sentences[:2]) + ' ' + sentences[-1]
    return summary

def send_email_digest(email, articles):
    """Send email digest with improved formatting and links"""
    logger.info(f"Preparing email for {email} with {len(articles)} articles")

    ORIGIN_EMAIL = os.getenv("ORIGIN_EMAIL")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

    # Validate environment variables
    if not ORIGIN_EMAIL:
        logger.error("ORIGIN_EMAIL environment variable is not set")
        raise ValueError("Email sender address not configured in environment variables")

    if not EMAIL_PASSWORD:
        logger.error("EMAIL_PASSWORD environment variable is not set")
        raise ValueError("Email password not configured in environment variables")

    # Create HTML email
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Your News Digest'
    msg['From'] = ORIGIN_EMAIL
    msg['To'] = email

    # Create plain text version
    text_content = "Your News Digest\n\n"

    for i, article in enumerate(articles, 1):
        text_content += f"ARTICLE {i}: {article['title']}\n"
        text_content += f"Source: {article.get('source', 'Unknown')}\n"

        if article.get('url'):
            text_content += f"Link: {article['url']}\n"

        if article.get('publishedAt'):
            # Try to format date if possible
            try:
                date = datetime.fromisoformat(article['publishedAt'].replace('Z', '+00:00'))
                text_content += f"Published: {date.strftime('%B %d, %Y')}\n"
            except:
                text_content += f"Published: {article['publishedAt']}\n"

        text_content += "\n"

        if article.get('summary'):
            text_content += f"Summary: {article['summary']}\n"

        text_content += "\n" + "-"*40 + "\n\n"

    text_content += "\nPowered by DigestAI"

    # Create HTML version
    html_content = """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; }
            h1 { color: #2c3e50; border-bottom: 1px solid #eee; padding-bottom: 10px; }
            h2 { color: #2980b9; }
            .article { margin-bottom: 30px; border-bottom: 1px solid #eee; padding-bottom: 20px; }
            .source { color: #7f8c8d; font-style: italic; margin-bottom: 10px; }
            .date { color: #7f8c8d; margin-bottom: 15px; }
            .summary { line-height: 1.8; }
            .read-more { display: inline-block; margin-top: 10px; color: #3498db; text-decoration: none; font-weight: bold; }
            .footer { margin-top: 30px; color: #7f8c8d; font-size: 0.9em; }
        </style>
    </head>
    <body>
        <h1>Your News Digest</h1>
    """

    for article in articles:
        html_content += f"<div class='article'>"
        html_content += f"<h2>{article['title']}</h2>"
        html_content += f"<div class='source'>Source: {article.get('source', 'Unknown')}</div>"

        if article.get('publishedAt'):
            # Try to format date if possible
            try:
                date = datetime.fromisoformat(article['publishedAt'].replace('Z', '+00:00'))
                html_content += f"<div class='date'>Published: {date.strftime('%B %d, %Y')}</div>"
            except:
                html_content += f"<div class='date'>Published: {article['publishedAt']}</div>"

        if article.get('summary'):
            html_content += f"<div class='summary'>{article['summary']}</div>"

        if article.get('url'):
            html_content += f"<a href='{article['url']}' class='read-more'>Read Full Article</a>"

        html_content += "</div>"

    html_content += """
        <div class='footer'>Powered by DigestAI</div>
    </body>
    </html>
    """

    # Attach both text and HTML versions
    part1 = MIMEText(text_content, 'plain')
    part2 = MIMEText(html_content, 'html')
    msg.attach(part1)
    msg.attach(part2)

    # Send email
    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(ORIGIN_EMAIL, EMAIL_PASSWORD)
        server.sendmail(ORIGIN_EMAIL, email, msg.as_string())
        server.quit()
        logger.info(f"✅ Email successfully sent to {email}")
    except Exception as e:
        logger.error(f"❌ Error sending email: {e}")
        raise ValueError(f"Failed to send email: {str(e)}")

# For directly running the script
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5001))
    logger.info(f"Starting FastAPI server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
