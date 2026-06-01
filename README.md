# Autonomous Invoice Processing & Spend Categorization Crew

An intelligent, multi-agent automated financial processing system built on **CrewAI** and managed with **Astral `uv`**. This project replaces rigid, fragile regex-based document parsing with a flexible, highly accurate multi-agent assembly line that reads invoices and automatically codes them to a strict corporate chart of accounts.

---

## 🏗 System Architecture

Instead of relying on a single AI model to extract data, evaluate compliance, and pick a category all at once—which heavily invites hallucinations—this project implements a **deterministic 3-stage financial pipeline**:


## 🧪 Verification & Testing

To ensure that the multi-agent system extracts data cleanly, verifies calculations accurately, and strictly conforms to your corporate schema, you can run automated verification tests.

### 1. Fast Pipeline Verification (Smoke Test)
You can instantly verify that the environment, CrewAI workflows, and LLM providers are talking to each other by running the built-in demo extraction task:

```bash
uv run main.py