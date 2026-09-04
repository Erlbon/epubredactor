"""
core/genres.py

A curated list of common genre/subject labels, used to populate a
quick-pick dropdown next to the free-text Tags/Genre field. This is a
convenience shortlist, not a controlled vocabulary -- the field always
stays free text, so anything not on this list can still be typed
directly. Written independently rather than sourced from any
third-party classification system (e.g. BISAC): individual genre names
are ordinary descriptive words, but BISG's own maintained subject-code
list itself is licensed and its terms don't permit redistributing it in
third-party software, so this list deliberately doesn't reproduce it.
"""

COMMON_GENRES: list[str] = sorted([
    # Fiction, broad
    "Fiction",
    "Literary Fiction",
    "Contemporary Fiction",
    "Historical Fiction",
    "Women's Fiction",
    "Satire",
    "Magical Realism",
    "Coming of Age",
    "New Adult",
    "Young Adult",
    "Children's",
    "Middle Grade",
    "Picture Book",
    "Classics",

    # Fantasy
    "Fantasy",
    "Epic Fantasy",
    "High Fantasy",
    "Dark Fantasy",
    "Urban Fantasy",
    "Sword & Sorcery",
    "Fairy Tale Retelling",
    "Portal Fantasy",
    "Fantasy Romance",

    # Science fiction
    "Science Fiction",
    "Hard Science Fiction",
    "Space Opera",
    "Cyberpunk",
    "Dystopian",
    "Post-Apocalyptic",
    "Time Travel",
    "Alternate History",
    "Military Science Fiction",
    "First Contact",

    # Mystery, crime & thriller
    "Mystery",
    "Cozy Mystery",
    "Detective",
    "Police Procedural",
    "Crime",
    "True Crime",
    "Noir",
    "Heist",
    "Thriller",
    "Psychological Thriller",
    "Legal Thriller",
    "Spy Thriller",

    # Horror
    "Horror",
    "Gothic",
    "Supernatural",
    "Ghost Story",

    # Romance
    "Romance",
    "Contemporary Romance",
    "Historical Romance",
    "Paranormal Romance",
    "Romantic Comedy",
    "Romantic Suspense",
    "Erotica",

    # Adventure & action
    "Adventure",
    "Action",
    "War",
    "Western",
    "Survival",

    # Format / structure
    "Graphic Novel",
    "Comics",
    "Light Novel",
    "Novella",
    "Short Stories",
    "Anthology",
    "Fan Fiction",

    # Poetry, drama & humor
    "Poetry",
    "Drama",
    "Humor",

    # Biography & memoir
    "Biography",
    "Memoir",
    "Autobiography",
    "Letters & Diaries",

    # History, politics & society
    "History",
    "Military History",
    "Politics",
    "Current Affairs",
    "Social Science",
    "Anthropology",
    "Law",

    # Science, technology & nature
    "Science",
    "Technology",
    "Mathematics",
    "Nature",
    "Environment",
    "Medicine",

    # Philosophy & religion
    "Philosophy",
    "Religion & Spirituality",
    "Mythology",

    # Self-help & personal
    "Self-Help",
    "Psychology",
    "Health & Wellness",
    "Parenting",
    "Relationships",

    # Business & economics
    "Business",
    "Economics",
    "Finance",
    "Leadership",
    "Entrepreneurship",

    # Arts, culture & lifestyle
    "Art & Design",
    "Music",
    "Photography",
    "Film & Media",
    "Fashion",
    "Travel",
    "Cooking",
    "Gardening",
    "Crafts & Hobbies",
    "Sports & Recreation",

    # Reference & education
    "Reference",
    "Education",
    "Language Learning",
    "Textbook",

    # Nonfiction, broad
    "Nonfiction",
    "Essays",
])


def add_genre(current: str, genre: str) -> str:
    """Append `genre` to a semicolon-separated list `current`, without
    duplicating it if it's already present. Pure string logic, no GUI --
    used by the quick-pick dropdown so a value picked from the list is
    added alongside whatever's already typed, never replacing it."""
    parts = [p.strip() for p in current.split(";") if p.strip()]
    if genre not in parts:
        parts.append(genre)
    return "; ".join(parts)
