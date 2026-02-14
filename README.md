# X Automation Agent

Automated reply system for X (Twitter) using human-in-the-loop workflow.

## Features

- ✅ Manual link injection (Grok-compatible)
- ✅ Human-like delays (60-180s)
- ✅ Smart reply generation (OpenAI)
- ✅ Duplicate detection
- ✅ Daily limits (50 replies)
- ✅ Batch processing
- ✅ Web UI

## Quick Start

### 1. Setup Environment

Copy `.env.example` to `.env` and add your API keys:

```bash
cp .env.example .env
```

Edit `.env` with your:
- X API credentials
- OpenAI API key

### 2. Run with Docker (Recommended)

```bash
docker-compose up -d
```

Access UI: http://localhost:8000

### 3. Run Locally

```bash
pip install -r requirements.txt
python main.py
```

## Usage

1. Get post links from Grok or manually
2. Paste links in the web UI (one per line)
3. Set target reply count
4. Click "Start Automation"
5. Monitor progress in real-time

## Safety Features

- **Rate Limiting**: Daily 50 reply limit
- **Smart Delays**: Random 60-180s between replies
- **Batch Breaks**: 10-15 min break every 10 replies
- **Duplicate Check**: Won't reply twice to same post
- **Similarity Detection**: Unique replies every time

## Troubleshooting

See `automation.db` for processed posts and logs.

## License

MIT
