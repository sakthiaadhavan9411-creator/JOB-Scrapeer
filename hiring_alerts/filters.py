from collections.abc import Sequence

from .models import Post


def matches(post: Post, include: Sequence[str], exclude: Sequence[str],
            roles: Sequence[str] = ()) -> bool:
    haystack = " ".join((post.title, post.author, post.text)).casefold()
    # Roles must appear in the post itself, not merely in the author's job title.
    role_text = " ".join((post.title + " " + post.text).casefold().replace("’", "'").split())
    role_match = not roles or any(" ".join(k.casefold().replace("’", "'").split()) in role_text for k in roles)
    return role_match and (not include or any(k.casefold() in haystack for k in include)) and not any(
        k.casefold() in haystack for k in exclude
    )
