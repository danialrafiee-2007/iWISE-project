---
title: Truth Guardian
colorFrom: gray
colorTo: green
sdk: docker
app_port: 7860
pinned: false
short_description: Hallucination detection for RAG and agent answers
---

# Truth Guardian

Checks an AI answer against its sources, claim by claim: grounded or hallucinated, a calibrated risk, the exact
words that are wrong, the evidence, and a fix. It also traces where an agent's run went wrong. Entry for the iWISE
2026 AI & Web Programming Challenge, AI Challenge 4.

The app runs entirely inside this Space on open models (no paid API). The image is built from the project's
Dockerfile; the first start after a build takes a minute or two while the models load. Press **Tour** in the top bar
for a three-minute walk through every tool.

If the Space asks for a user name and password, use any user name and the access code you were given.
