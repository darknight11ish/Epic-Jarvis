- **Send one file from the PC to the phone:** ask Jarvis in chat to find a file
  in the folders it may look in and send it to the Jarvis phone app. ONE
  approval card shows the exact filename, folder and byte size; after the yes
  the phone fetches it by an opaque id - never a path - within ten minutes and
  once only, at most 10 MiB (bigger files are refused in words). The phone's own
  half is built: Settings -> "File from your PC" lists the approved files in the
  PC's words and can **View** one (handed to Android's viewer through the app's
  own FileProvider) or **Save to Downloads** (into `Downloads/Jarvis`, through
  MediaStore); a small "File from your PC" block appears inside Coming up on
  Brain so a waiting file is noticed, and while "Hide memory lists and chat
  history" is on no filename is fetched or drawn. The phone never approves a
  file and no route here ever carries a path (Gemini Q7; docs/JARVIS-API.md
  section 172).
