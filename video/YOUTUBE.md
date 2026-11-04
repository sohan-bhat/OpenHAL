# YouTube upload

Text for the demo video's YouTube page. Upload `video/out/openhal-demo-1440p.mp4` with the thumbnail `video/out/thumbnail.png`. Nothing here is uploaded yet. The end card shows `uvx halkit demo`, which works once OpenHAL 0.1.0 is on PyPI, so the video goes up after that release.

## Title

An open-source protocol for AI agents to control hardware. | OpenHAL

## Description

OpenHAL is an open-source protocol for AI agents to discover, read and control hardware, with a hub that checks every command against the limits in the device's file before the device sees the command.
Code and docs at https://github.com/sohan-bhat/OpenHAL

Claude Code drives a simulated SO-101 robot arm through the OpenHAL hub. The hub runs the pick, holds the drop into the bin until a person approves the drop in the OpenHAL Inspector, blocks a request at 120 deg/s with LIMIT_EXCEEDED because the arm's device file allows 60 deg/s, and holds the arm still when a person presses STOP. Every prompt, tool name, hub answer and arm motion comes from one recorded session of the real hub. The arm is simulated in MuJoCo.

Try it with `uvx halkit demo`.
Docs at https://sohan-bhat.github.io/OpenHAL/

0:00 Claude Code picks up the cube
0:13 The drop waits for a person, then a request past the limit
0:28 STOP, and other hardware

Credits
Music "Inspired" by Kevin MacLeod (incompetech.com), licensed under Creative Commons Attribution 4.0, https://creativecommons.org/licenses/by/4.0/
Stepper motor recording by dklon, OpenGameArt, CC BY 3.0
Keyboard recording by C40115, Wikimedia Commons, CC BY 4.0
Mouse click by Darklanlan (CC0) and switch by stephan (public domain), Wikimedia Commons
SO-101 model from MuJoCo Menagerie and The Robot Studio, Apache License 2.0
Desk texture Wood Table 001 and studio HDRI Studio Small 09, Poly Haven, CC0
IBM Plex Sans and IBM Plex Mono, SIL Open Font License 1.1
Made with Remotion and React Three Fiber
Not affiliated with Anthropic

## Tags

OpenHAL, AI agents, hardware, robotics, robot arm, SO-101, MCP, Model Context Protocol, Claude Code, safety, device limits, MuJoCo, open source, protocol

## Chapters

YouTube needs the first chapter at 0:00, at least three chapters and at least 10 seconds in each, so each chapter holds two or more scenes. The timestamps round each scene's first frame down to the second.

| Chapter | Starts | Scenes | First frame |
|---|---|---|---|
| Claude Code picks up the cube | 0:00 | ask, pick | 0.00 s |
| The drop waits for a person, then a request past the limit | 0:13 | held, drop, limit | 13.67 s |
| STOP, and other hardware | 0:28 | stop, stats, devices, end | 28.80 s |
