import express, { Request, Response } from "express";

const router = express.Router();

// Define the request body interface
interface NewsRequest {
  query: string;
  email: string;
  num_articles: number;
}

router.post("/sendDigest", async (req: any, res: any) => {
  try {
    const { query, email, num_articles = 5 } = req.body as NewsRequest;

    console.log("➡️ Express received request:", { query, email, num_articles });

    // Define the URL of your Python FastAPI server
    const pythonApiUrl = process.env.PYTHON_API_URL || "http://localhost:5001";

    try {
      console.log(
        `Forwarding request to Python API: ${pythonApiUrl}/api/sendDigest`
      );

      const response = await fetch(`${pythonApiUrl}/api/sendDigest`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query, email, num_articles }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error(`Error from Python API (${response.status}):`, errorText);

        // Check if the Python server is running
        return res.status(response.status).json({
          status: "error",
          message: `Python API returned status ${response.status}`,
          details: errorText,
        });
      }

      const data = await response.json();
      console.log("Response from Python API:", data);

      return res.json(data);
    } catch (error) {
      console.error("Error connecting to Python API:", error);

      return res.status(503).json({
        status: "error",
        message: "Failed to connect to Python API server. Is it running?",
        details: (error as Error).message,
      });
    }
  } catch (error) {
    console.error("Request parsing error:", error);

    return res.status(400).json({
      status: "error",
      message: "Invalid request data",
    });
  }
});

export default router;
