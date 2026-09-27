#!/bin/bash
# The fixed set of pure files and tests for the voice-phone builder. Extra test names may be passed.
# Copied from ../phonep/run-main.sh and pointed at this agent's worktree.
cd /home/user/Epic-Jarvis/jarvis-client/app
M=src/main/java/com/jarvis/client
T=src/test/java/com/jarvis/client
SRC="$M/net/ActivityEvent.kt $M/net/ApiModels.kt $M/net/BigModel.kt $M/net/ChatChunkParser.kt $M/net/ChatHistory.kt $M/net/ChatPicture.kt $M/net/Learning.kt $M/net/NoteCapture.kt $M/net/PendingRows.kt $M/net/SecondCard.kt $M/net/SseParser.kt $M/net/TaskControl.kt $M/net/VoiceModels.kt $M/net/Wiki.kt $M/voice/SmartTurn.kt $M/voice/SpeechText.kt $M/voice/VoiceFlow.kt $M/voice/StopWord.kt $M/voice/VoiceTraining.kt $M/voice/WakeRules.kt $M/voice/WakeSpotter.kt"
for f in src/main/java/com/jarvis/client/data/Security.kt $M/net/UpdateCheck.kt $M/net/Approvals.kt $M/net/JobFollow.kt $M/net/DesktopWrite.kt $M/net/Watch.kt $M/net/Skills.kt $M/net/Steps.kt $M/net/MemoryCounts.kt $M/net/CustomVoices.kt $M/net/VoiceStrict.kt $M/voice/StrictVoice.kt $M/voice/VoiceRounds.kt $M/voice/PrivateAloud.kt $M/voice/SpeechAhead.kt $M/net/Provenance.kt $M/net/ChatLog.kt $M/net/AutoLearn.kt $M/net/MemoryErase.kt $M/net/MemoryProfile.kt $M/net/MemoryUsed.kt $M/net/Hardware.kt $M/net/Schedule.kt $M/net/Briefing.kt $M/net/WebSearch.kt $M/net/Reach.kt $M/net/EmailSending.kt $M/net/Manner.kt $M/net/PlainErrors.kt $M/net/CardWords.kt $M/voice/CardVoice.kt $M/net/StopEverything.kt $M/net/Focus.kt $M/net/TemporaryChat.kt $M/net/AsksFirst.kt $M/net/MemoryWords.kt $M/net/AlsoOnPhone.kt $M/net/Folders.kt $M/net/Wellbeing.kt $M/audio/Wav.kt; do [ -f "$f" ] && SRC="$SRC $f"; done
TESTS="SpeechTextTest MemoryAsOfTest JobFollowTest StopWordTest WakeListenTest NoteCaptureTest SecondCardContractTest BigModelContractTest VoiceTrainingTest MemoryDatesTest LearningTest ChatPictureContractTest WikiContractTest $*"
TSRC=""
TCLS=""
for t in $TESTS; do [ -f "$T/$t.kt" ] && { TSRC="$TSRC $T/$t.kt"; TCLS="$TCLS com.jarvis.client.$t"; }; done
bash /tmp/claude-0/-home-user-Epic-Jarvis/786d7fdd-6b1c-5483-a32b-fd87a501a213/scratchpad/mainphone/build-main.sh "$SRC $TSRC" "$TCLS" 2>&1 | grep -v JAVA_TOOL
