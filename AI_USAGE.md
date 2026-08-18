# AI usage

I used Claude to design and write most of this project — the Django pipeline,
the matching logic, the Expo screens — working through it prompt by prompt and
reviewing every change, including catching a crop-rotation bug that was making
the model misread spines. I used Claude to research and generate the first part
of `catalog.csv` (commonly owned and Canadian titles) and Gemini to fill gaps in
that list, then pulled the remaining entries from published Publishers Weekly
and Goodreads Choice Award lists so the rows would be verifiable rather than
invented. The local detector is off-the-shelf YOLOv8n from Ultralytics, chosen
after benchmarking it on CPU against my own shelf photos; nothing was trained or
fine-tuned. The hosted vision-language model is Claude Haiku 4.5, which reads
title and author off each spine crop. I can explain and modify any line in the
repository.
