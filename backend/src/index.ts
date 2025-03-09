import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import digestRoute from "./routes/digest";

dotenv.config();
const app = express();

app.use(cors());
app.use(express.json());

app.use("/digest", digestRoute);

app.listen(5001, () => console.log("Server is running on port 5001"));
