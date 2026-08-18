# AI usage

I built this project with help from Claude for the Django pipeline, matching logic, and Expo screens, reviewing and refining the code as I went.

For the catalog dataset, I used Claude and Gemini to draft an initial list of common books Canadians would own. Then supplemented it with award winning books from the last 10 years found by Claude.

The local detection uses an off-the-shelf YOLOv8n model from Ultralytics, selected after testing CPU performance on photos of my own bookshelf. For the vision-language model, I used Claude Haiku 4.5 to extract the title and author from each spine crop.
