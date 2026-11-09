# Photo Match

Copy any photo's look. Upload a reference photo and the app tells you how it was shot: angle, light, lens, pose. Upload your own photo next to it and you get a match analysis plus a Lightroom Classic preset (.xmp) that pushes your photo toward the reference, covering the basic panel, HSL, colour grading and vignette. You can run the same request through more than one AI engine and compare their reads side by side.

## Run it

Needs Python 3.9 or newer.

```
pip install -r requirements.txt
cp .env.example .env    # add the keys for the engines you want
python3 app.py
```

Open http://127.0.0.1:5000.

Engines:

- Claude (`ANTHROPIC_API_KEY`), paid.
- Llama 3.2 Vision through Ollama, free and local: `ollama pull llama3.2-vision`, no key needed.
- GPT-4o (`OPENAI_API_KEY`), paid.

The app runs with whichever engines are set up. The local model only takes one image per message, so for matching the app stitches the reference and your photo side by side into one image.

## Status

Working, run locally. Things to know:

- The preset leaves white balance out on purpose, because RAW and JPEG files store it differently. White balance advice comes as written notes instead.
- A preset gets you most of the way, then you fine-tune by hand. The AI matches by eye, not by measured values.
- The GPT engine and the AI re-edit (`/edit`, OpenAI's gpt-image-1) are in the backend but hidden in the UI right now. gpt-image-1 needs OpenAI organization verification before it will run.
- Flask runs in debug mode, so it's meant for your own machine, not a public server.

Portfolio: https://thejungjulian-del.github.io/portfolio/
