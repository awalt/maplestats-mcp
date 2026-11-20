"""feedback_: draft a bug report for the maintainers, ready for the user to approve.

Not a data source, and it sends nothing: the tool writes the report (title and
body in the repository's bug form, the server version filled in, keys, tokens,
email addresses and home-folder paths removed) and returns a link that opens
GitHub's form already filled in. The user reads the text and files it, or the
assistant files it with a GitHub tool after the user approves it
(docs://report-issue). The server keeps no copy.
"""

MODULE_NAME = "feedback"
MODULE_DESCRIPTION = (
    "Feedback: when a tool misbehaves, draft a bug report for the maintainers (title, body, "
    "server version, private details removed) with a link that opens GitHub's issue form "
    "already filled in. Nothing is sent or stored: the user approves and files it."
)
MODULE_DESCRIPTION_FR = (
    "Rétroaction : quand un outil se comporte mal, rédige un rapport de bogue pour les "
    "responsables (titre, corps, version du serveur, détails privés retirés) avec un lien qui "
    "ouvre le formulaire de GitHub déjà rempli. Rien n'est envoyé ni conservé : l'utilisateur "
    "approuve et dépose le rapport."
)
