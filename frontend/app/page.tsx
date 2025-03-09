"use client";
import React, { useState, FormEvent } from "react";

export default function Home() {
  const [query, setQuery] = useState("");
  const [email, setEmail] = useState("");
  const [numArticles, setNumArticles] = useState(5);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const response = await fetch("/api/sendDigest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, email, num_articles: numArticles }),
    });

    const result = await response.json();
    console.log(result);
  };

  return (
    <form onSubmit={handleSubmit}>
      <input
        value={query}
        placeholder="query"
        onChange={(e) => setQuery(e.target.value)}
      />
      <input
        type="email"
        placeholder="Your email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <input
        type="number"
        value={numArticles}
        onChange={(e) => setNumArticles(parseInt(e.target.value, 10))}
        placeholder="Articles count"
      />
      <button type="submit">Send Digest</button>
    </form>
  );
}
