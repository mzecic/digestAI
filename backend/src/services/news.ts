import axios from "axios";
import * as cheerio from "cheerio";
import nodemailer from "nodemailer";

interface Article {
  title: string;
  content: string;
}

/**
 * Scrape articles based on a search query
 */
export async function scrapeArticles(
  query: string,
  numArticles: number
): Promise<Article[]> {
  try {
    const url = `https://www.bing.com/news/search?q=${encodeURIComponent(
      query
    )}`;
    const response = await axios.get(url, {
      headers: { "User-Agent": "Mozilla/5.0" },
    });

    const $ = cheerio.load(response.data);
    const articles: Article[] = [];

    // Find article links
    const cardLinks = $("a.title").slice(0, numArticles);

    for (let i = 0; i < cardLinks.length; i++) {
      const element = cardLinks[i];
      const title = $(element).text().trim();
      let link = $(element).attr("href") || "";

      if (!link.startsWith("http")) {
        link = "https://www.bing.com" + link;
      }

      try {
        const contentResponse = await axios.get(link, {
          headers: { "User-Agent": "Mozilla/5.0" },
        });

        const contentPage = cheerio.load(contentResponse.data);
        const paragraphs = contentPage("p");

        let content = "";
        paragraphs.each((_, para) => {
          const text = contentPage(para).text().trim();
          if (text) {
            content += text + " ";
          }
        });

        articles.push({ title, content });
      } catch (err) {
        console.error(`Error fetching article content for ${link}:`, err);
      }
    }

    return articles;
  } catch (error) {
    console.error("Error scraping articles:", error);
    throw new Error("Failed to scrape articles");
  }
}

/**
 * Summarize article content using Hugging Face API
 */
export async function summarize(text: string): Promise<string> {
  const HUGGINGFACE_API_KEY = process.env.HUGGINGFACE_API_KEY;

  if (!HUGGINGFACE_API_KEY) {
    return "API key not configured. Summary unavailable.";
  }

  try {
    const API_URL =
      "https://api-inference.huggingface.co/models/facebook/bart-large-cnn";
    const response = await axios.post(
      API_URL,
      {
        inputs: text.slice(0, 1024),
        parameters: { max_length: 150, min_length: 50, do_sample: false },
      },
      {
        headers: {
          Authorization: `Bearer ${HUGGINGFACE_API_KEY}`,
          "Content-Type": "application/json",
        },
      }
    );

    if (response.status === 200 && response.data && response.data[0]) {
      return response.data[0].summary_text;
    } else {
      console.error("Summarization API error:", response.data);
      return "Summarization failed.";
    }
  } catch (error) {
    console.error("Error generating summary:", error);
    return "Error generating summary.";
  }
}

/**
 * Send email digest
 */
export async function sendEmailDigest(
  email: string,
  summaries: string[]
): Promise<void> {
  const ORIGIN_EMAIL = process.env.ORIGIN_EMAIL;
  const EMAIL_PASSWORD = process.env.EMAIL_PASSWORD;

  if (!ORIGIN_EMAIL || !EMAIL_PASSWORD) {
    throw new Error("Email credentials not configured");
  }

  const emailBody = summaries.join("\n\n") || "No summaries available.";

  const transporter = nodemailer.createTransport({
    host: "smtp.gmail.com",
    port: 465,
    secure: true,
    auth: {
      user: ORIGIN_EMAIL,
      pass: EMAIL_PASSWORD,
    },
  });

  const mailOptions = {
    from: ORIGIN_EMAIL,
    to: email,
    subject: "Your daily news digest",
    text: emailBody,
  };

  try {
    await transporter.sendMail(mailOptions);
  } catch (error) {
    console.error("Error sending email:", error);
    throw new Error("Failed to send email");
  }
}
