# Troubleshooting

## Model or ASR dependency missing

Run `doctor --json`. If the user approves the download, run `setup --model balanced`; use `fast` to select the smaller model. Model files stay under the configured data directory.

## `DECODER_UNAVAILABLE` or media has no audio

The ASR extra includes PyAV. Install it using the explicit setup flow. The input must contain a decodable audio stream; a silent or video-only file cannot produce a transcript.

## `LOGIN_REQUIRED`

Run the URL task again and sign in manually in the opened persistent Chromium profile. The tool does not automate authentication or bypass verification.

## `CAPTURE_NO_MEDIA` or download failure

The page may have changed, the user may not have access, or the current media host may not be supported. Use an authorized local audio/video file as a fallback. Do not copy signed media URLs or browser cookies into logs or support tickets.

## Output collision or invalid completed output

Default behavior preserves existing files. Use `--force` to rerun and save a separate file. Inspect or move files manually if the destination directory is not writable.

## Windows path or disk space

Set `DOUYIN_TRANSCRIPT_HOME` to a writable directory, for example `D:\douyin-transcript-data`. `doctor` checks the closest existing parent without creating the requested directory.

## Private storage warning

`doctor` reports permission checks for the data directory, task database, browser profile, and media cache. New POSIX storage uses mode `0700` for directories and `0600` for the SQLite database. Windows uses a protected DACL based on the current process token's user SID; it does not infer identity from a username. Existing broad permissions are never rewritten automatically. If an existing data directory or database is reported as `unsafe` or `unknown`, choose a new private data directory and point `DOUYIN_TRANSCRIPT_HOME` or `--data-dir` to it. Do not place the persistent browser profile in a shared or synchronized folder: it can contain login cookies and other browser state. The tool does not apply these protections to the user-selected transcript output directory.

If private directory or database creation fails during an identity or permission check, the error explains that a newly created private empty object may remain. A parent directory may also have moved while the check was running, so the leftover object may no longer appear at the original path. Do not delete a suspected leftover using its old pathname alone; inspect the containing directory and confirm the object's identity first. The program intentionally does not perform a name-based rollback that could remove a replacement object.
