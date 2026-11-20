### Added

- `feedback_draft_issue`: when a tool misbehaves, drafts the bug report for the
  maintainers in the repository's bug form, with the server version filled in
  (a hosted user could not look it up) and keys, tokens, email addresses and
  home-folder paths removed, saying what was removed. `issue_url` opens GitHub's
  form with the fields already filled in (the title only when the text is too
  long for a link), and `search_url` lists open issues on the same tool. Nothing
  is sent or stored: the user approves the exact text and files it, as
  docs://report-issue sets out.
