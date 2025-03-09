import express from "express";
import axios from "axios";

const router = express.Router();

router.post("/api/sendDigest", async (req, res) => {
  const { query, email, num_articles } = req.body;
  try {
    const response = await axios.post("http://localhost:8000/api/sendDigest", {
      query,
      num_articles,
      email,
    });
    res.json({ message: "Digest is being generated", data: response.data });
  } catch (error) {
    res.status(500).json({ message: "Internal server error" });
  }
});

export default router;
