"""EPUB 3 metadata writing (2026-11-02): no dangling refines, no EPUB 2
opf: attributes in an EPUB 3 package, EPUB 2 output unchanged.

Found on a pandoc-built EPUB 3 (Saw Hammer v20.1 RC2): saving rebuilt
dc:creator without its id, leaving <meta refines="#epub-creator-1"> pointing
at nothing (an EPUBCheck error), and wrote opf:file-as / opf:role /
opf:authority attributes, which EPUB 3 does not allow."""
import zipfile

from lxml import etree

from core.epub_metadata import NS, EpubBook

OPF_NS = NS["opf"]
DC_NS = NS["dc"]

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

CHAP1 = "<html><body><p>Hello world</p></body></html>"

MANIFEST = """
  <manifest>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chap1"/>
  </spine>
</package>
"""

# The shape pandoc writes: ids on the elements, roles as refining metas.
PANDOC_EPUB3_METADATA = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="epub-id-1">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="epub-id-1">urn:uuid:2ce9bcff-58f9-490c-ba35-8e5a5da60fd5</dc:identifier>
    <dc:title id="epub-title-1">Saw Hammer</dc:title>
    <meta refines="#epub-title-1" property="title-type">main</meta>
    <dc:date id="epub-date">2026-11-02</dc:date>
    <dc:language>en-GB</dc:language>
    <dc:creator id="epub-creator-1">Allan Lawson</dc:creator>
    <meta refines="#epub-creator-1" property="role" scheme="marc:relators">aut</meta>
    <dc:creator id="epub-creator-2">Tom Tolk</dc:creator>
    <meta refines="#epub-creator-2" property="role" scheme="marc:relators">trl</meta>
    <meta refines="#epub-creator-2" property="file-as">Tolk, Tom</meta>
    <dc:contributor id="epub-contributor-1">Augusta Irving Claude</dc:contributor>
    <meta refines="#epub-contributor-1" property="role" scheme="marc:relators">edt</meta>
    <dc:subject id="epub-subject-1">Fiction</dc:subject>
    <meta refines="#epub-subject-1" property="authority">BISAC</meta>
    <meta refines="#epub-subject-1" property="term">FIC000000</meta>
    <dc:publisher>Pendulum SF</dc:publisher>
    <meta property="dcterms:modified">2026-11-02T13:15:01Z</meta>
  </metadata>"""

# What the old code saved into that book (the RC2 as found): attributes on
# the rebuilt creator and DDC subject, and the creator's role meta dangling.
OLD_SAVED_EPUB3_METADATA = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="epub-id-1">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="epub-id-1">urn:uuid:2ce9bcff-58f9-490c-ba35-8e5a5da60fd5</dc:identifier>
    <dc:title id="epub-title-1">Saw Hammer</dc:title>
    <dc:language>en-GB</dc:language>
    <meta refines="#epub-creator-1" property="role" scheme="marc:relators">aut</meta>
    <dc:contributor id="epub-contributor-1">Augusta Irving Claude</dc:contributor>
    <meta refines="#epub-contributor-1" property="role" scheme="marc:relators">edt</meta>
    <meta property="dcterms:modified">2026-11-02T13:15:01Z</meta>
  <dc:creator opf:file-as="Lawson, Allan" opf:role="aut">Allan Lawson</dc:creator><dc:subject>Fiction</dc:subject><dc:subject opf:authority="DDC">823.914</dc:subject></metadata>"""

EPUB2_METADATA = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:abcd-1234</dc:identifier>
    <dc:title>Old Book</dc:title>
    <dc:language>en</dc:language>
    <dc:creator opf:role="aut">Allan Lawson</dc:creator>
    <dc:creator opf:role="trl" opf:file-as="Tolk, Tom">Tom Tolk</dc:creator>
    <dc:subject>Fiction</dc:subject>
  </metadata>"""

# The EPUB 2 OPF metadata the writer produced before this change, for the
# edit made in test_epub2_output_unchanged (captured from the old code),
# except that the translator keeps opf:role="trl" instead of being turned
# into "aut".
EPUB2_EXPECTED = (
    '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf"'
    ' xmlns="http://www.idpf.org/2007/opf">\n'
    '    <dc:identifier id="BookId">urn:uuid:abcd-1234</dc:identifier>\n'
    '    <dc:title>Old Book</dc:title>\n'
    '    <dc:language>en</dc:language>\n'
    '    <dc:creator opf:file-as="Lawson, Allan" opf:role="aut">Allan Lawson</dc:creator>'
    '<dc:creator opf:file-as="Tolk, Tom" opf:role="trl">Tom Tolk</dc:creator>'
    '<dc:subject>Fiction</dc:subject>'
    '<dc:subject opf:authority="DDC">823.914</dc:subject></metadata>\n  '
)


def build_epub(path, metadata_xml):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("EPUB/content.opf", metadata_xml + MANIFEST)
        zf.writestr("EPUB/chap1.xhtml", CHAP1)
    return str(path)


def read_opf(path):
    with zipfile.ZipFile(path) as zf:
        return etree.fromstring(zf.read("EPUB/content.opf"))


def metadata_xml(path):
    md = read_opf(path).find("opf:metadata", namespaces=NS)
    return etree.tostring(md, encoding="unicode")


def save_with(path, **values):
    """The app's normal save path: load, apply field values, save in place."""
    book = EpubBook(path)
    assert book.load_error is None, book.load_error
    book.apply_metadata(values)
    book.dirty = True
    book.save()
    return book


def dangling_refines(root):
    ids = {el.get("id") for el in root.iter() if el.get("id")}
    return [
        m.get("refines")
        for m in root.iter(f"{{{OPF_NS}}}meta")
        if m.get("refines") and m.get("refines")[1:] not in ids
    ]


def opf_attributes(root):
    md = root.find("opf:metadata", namespaces=NS)
    return [
        (etree.QName(el).localname, etree.QName(a).localname)
        for el in md.iter()
        for a in el.attrib
        if a.startswith(f"{{{OPF_NS}}}")
    ]


def refining(root, el, prop):
    md = root.find("opf:metadata", namespaces=NS)
    el_id = el.get("id")
    assert el_id, f"{etree.QName(el).localname} {el.text!r} has no id"
    return [
        m.text for m in md.findall("opf:meta", namespaces=NS)
        if m.get("refines") == f"#{el_id}" and m.get("property") == prop
    ]


def creators(root):
    return {el.text: el for el in root.iter(f"{{{DC_NS}}}creator")}


def test_epub3_save_leaves_no_dangling_refines_and_no_opf_attributes(tmp_path):
    path = build_epub(tmp_path / "pandoc3.epub", PANDOC_EPUB3_METADATA)
    save_with(path, author_sort=["Lawson, Allan", "Tolk, Tom"], ddc="823.914")
    root = read_opf(path)
    assert dangling_refines(root) == []
    assert opf_attributes(root) == []

    by_name = creators(root)
    assert refining(root, by_name["Allan Lawson"], "file-as") == ["Lawson, Allan"]
    assert refining(root, by_name["Allan Lawson"], "role") == ["aut"]
    # The translator keeps its role (both creators are in the Authors field).
    assert refining(root, by_name["Tom Tolk"], "role") == ["trl"]
    assert refining(root, by_name["Tom Tolk"], "file-as") == ["Tolk, Tom"]
    role_metas = [m for m in root.iter(f"{{{OPF_NS}}}meta") if m.get("property") == "role"]
    assert all(m.get("scheme") == "marc:relators" for m in role_metas)

    subjects = {el.text: el for el in root.iter(f"{{{DC_NS}}}subject")}
    assert refining(root, subjects["823.914"], "authority") == ["DDC"]
    assert refining(root, subjects["823.914"], "term") == ["823.914"]
    # Untouched elements keep their refines: contributor, title.
    contributor = root.find(".//dc:contributor", namespaces=NS)
    assert refining(root, contributor, "role") == ["edt"]
    title = root.find(".//dc:title", namespaces=NS)
    assert refining(root, title, "title-type") == ["main"]


def test_epub3_removed_author_and_subject_take_their_refines_along(tmp_path):
    path = build_epub(tmp_path / "pandoc3.epub", PANDOC_EPUB3_METADATA)
    save_with(path, authors=["Allan Lawson"], author_sort=[], tags=[])
    root = read_opf(path)
    assert dangling_refines(root) == []
    assert "Tom Tolk" not in creators(root)
    assert not any(m.text == "FIC000000" for m in root.iter(f"{{{OPF_NS}}}meta"))


def test_epub3_removed_title_takes_its_refines_along(tmp_path):
    path = build_epub(tmp_path / "pandoc3.epub", PANDOC_EPUB3_METADATA)
    save_with(path, title="")
    assert dangling_refines(read_opf(path)) == []


def test_old_saved_epub3_still_reads_and_is_repaired_on_save(tmp_path):
    path = build_epub(tmp_path / "old3.epub", OLD_SAVED_EPUB3_METADATA)
    book = EpubBook(path)
    assert book.metadata.author_sort == ["Lawson, Allan"]
    assert book.metadata.ddc == "823.914"
    assert book.metadata.tags == ["Fiction"]

    save_with(path)
    root = read_opf(path)
    assert dangling_refines(root) == []
    assert opf_attributes(root) == []
    reread = EpubBook(path).metadata
    assert reread.author_sort == ["Lawson, Allan"]
    assert reread.ddc == "823.914"
    assert reread.tags == ["Fiction"]


def test_epub3_reads_refines_form(tmp_path):
    path = build_epub(tmp_path / "pandoc3.epub", PANDOC_EPUB3_METADATA)
    md = EpubBook(path).metadata
    assert md.authors == ["Allan Lawson", "Tom Tolk"]
    assert md.author_sort == ["", "Tolk, Tom"]
    assert md.tags == ["Fiction"]  # a BISAC subject is a tag, not a DDC


def test_epub2_output_unchanged(tmp_path):
    path = build_epub(tmp_path / "old2.epub", EPUB2_METADATA)
    save_with(path, author_sort=["Lawson, Allan", "Tolk, Tom"], ddc="823.914")
    assert metadata_xml(path) == EPUB2_EXPECTED
    root = read_opf(path)
    assert not any(m.get("refines") for m in root.iter(f"{{{OPF_NS}}}meta"))


def test_isbn_epub3_is_a_urn_without_opf_scheme(tmp_path):
    path = build_epub(tmp_path / "pandoc3.epub", PANDOC_EPUB3_METADATA)
    save_with(path, isbn="9780141439518")
    root = read_opf(path)
    assert opf_attributes(root) == []
    texts = [el.text for el in root.iter(f"{{{DC_NS}}}identifier")]
    assert "urn:isbn:9780141439518" in texts
    assert EpubBook(path).metadata.isbn == "9780141439518"


def test_isbn_epub2_keeps_opf_scheme(tmp_path):
    path = build_epub(tmp_path / "old2.epub", EPUB2_METADATA)
    save_with(path, isbn="9780141439518")
    root = read_opf(path)
    isbn_el = [el for el in root.iter(f"{{{DC_NS}}}identifier") if el.text == "9780141439518"]
    assert isbn_el and isbn_el[0].get(f"{{{OPF_NS}}}scheme") == "ISBN"
    assert EpubBook(path).metadata.isbn == "9780141439518"


OTHER_TOOL_EPUB3_METADATA = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:eeee</dc:identifier>
    <dc:identifier opf:scheme="ISBN">9780141439518</dc:identifier>
    <dc:identifier opf:scheme="GOODREADS">12345</dc:identifier>
    <dc:title>Other Tool</dc:title>
    <dc:language>en</dc:language>
    <dc:date opf:event="publication">1999</dc:date>
    <dc:contributor opf:role="trl" opf:file-as="Tolk, Tom">Tom Tolk</dc:contributor>
  </metadata>"""


def codes(book):
    return {i.code for i in book.validation_issues}


def test_validate_flags_and_fixes_the_old_saved_epub3(tmp_path):
    path = build_epub(tmp_path / "old3.epub", OLD_SAVED_EPUB3_METADATA)
    book = EpubBook(path)
    assert {"DANGLING_REFINES", "EPUB2_ATTRIBUTES_IN_EPUB3"} <= codes(book)
    fixed = book.apply_fixes({"DANGLING_REFINES", "EPUB2_ATTRIBUTES_IN_EPUB3"})
    assert fixed and book.dirty
    assert not {"DANGLING_REFINES", "EPUB2_ATTRIBUTES_IN_EPUB3"} & codes(book)
    book.save()
    root = read_opf(path)
    assert dangling_refines(root) == [] and opf_attributes(root) == []
    reread = EpubBook(path)
    assert reread.metadata.author_sort == ["Lawson, Allan"]
    assert reread.metadata.ddc == "823.914"
    assert not {"DANGLING_REFINES", "EPUB2_ATTRIBUTES_IN_EPUB3"} & codes(reread)


def test_validate_fix_converts_other_tools_attributes(tmp_path):
    path = build_epub(tmp_path / "other3.epub", OTHER_TOOL_EPUB3_METADATA)
    book = EpubBook(path)
    assert "EPUB2_ATTRIBUTES_IN_EPUB3" in codes(book)
    assert "DANGLING_REFINES" not in codes(book)
    fixed = book.apply_fixes({"EPUB2_ATTRIBUTES_IN_EPUB3"})
    assert any("opf:event" in line for line in fixed)
    book.save()
    root = read_opf(path)
    assert opf_attributes(root) == [] and dangling_refines(root) == []
    contributor = root.find(".//dc:contributor", namespaces=NS)
    assert refining(root, contributor, "role") == ["trl"]
    assert refining(root, contributor, "file-as") == ["Tolk, Tom"]
    goodreads = [el for el in root.iter(f"{{{DC_NS}}}identifier") if el.text == "12345"][0]
    assert refining(root, goodreads, "identifier-type") == ["GOODREADS"]
    assert EpubBook(path).metadata.isbn == "9780141439518"


def test_epub2_attributes_are_not_flagged_in_epub2(tmp_path):
    book = EpubBook(build_epub(tmp_path / "old2.epub", EPUB2_METADATA))
    assert not {"DANGLING_REFINES", "EPUB2_ATTRIBUTES_IN_EPUB3"} & codes(book)


def test_round_trip_is_stable(tmp_path):
    for name, source in (("pandoc3.epub", PANDOC_EPUB3_METADATA),
                         ("old3.epub", OLD_SAVED_EPUB3_METADATA),
                         ("old2.epub", EPUB2_METADATA)):
        path = build_epub(tmp_path / name, source)
        save_with(path, author_sort=["Lawson, Allan"], ddc="823.914")
        first = metadata_xml(path)
        first_md = EpubBook(path).metadata.as_dict()
        save_with(path)
        assert metadata_xml(path) == first, name
        assert EpubBook(path).metadata.as_dict() == first_md, name
