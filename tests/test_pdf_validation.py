"""Exercise font validation against serialized PDF resource graphs."""

from importlib.resources import files

import pytest
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject

from bible_reader.models import ReaderError
from bible_reader.tex import verify_compilation


def pdf_dict(**entries):
    return DictionaryObject({NameObject("/" + name): value for name, value in entries.items()})


def font_resources(writer, *, embedded, indirect=True):
    font = pdf_dict(
        Type=NameObject("/Font"), Subtype=NameObject("/TrueType"), BaseFont=NameObject("/GentiumPlus")
    )
    if embedded:
        program = DecodedStreamObject()
        program.set_data(files("bible_reader").joinpath("resources/GentiumPlus-Regular.ttf").read_bytes())
        program[NameObject("/Length1")] = NumberObject(len(program.get_data()))
        descriptor = pdf_dict(
            Type=NameObject("/FontDescriptor"),
            FontName=NameObject("/GentiumPlus"),
            FontFile2=writer._add_object(program),
        )
        font[NameObject("/FontDescriptor")] = writer._add_object(descriptor)
    fonts = pdf_dict(F1=writer._add_object(font))
    return pdf_dict(Font=writer._add_object(fonts) if indirect else fonts)


def resource_pdf(path, *, embedded, category=None, indirect=True, cycle=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    resources = font_resources(writer, embedded=embedded, indirect=indirect)
    resource_ref = writer._add_object(resources)
    if category:
        nested = DecodedStreamObject()
        nested.set_data(b"")
        nested[NameObject("/Resources")] = resource_ref
        if category == "XObject":
            nested.update(
                pdf_dict(
                    Type=NameObject("/XObject"),
                    Subtype=NameObject("/Form"),
                    BBox=ArrayObject([NumberObject(n) for n in (0, 0, 200, 200)]),
                )
            )
        else:
            nested.update(
                pdf_dict(
                    Type=NameObject("/Pattern"),
                    PatternType=NumberObject(1),
                    PaintType=NumberObject(1),
                    TilingType=NumberObject(1),
                    BBox=ArrayObject([NumberObject(n) for n in (0, 0, 200, 200)]),
                    XStep=NumberObject(200),
                    YStep=NumberObject(200),
                )
            )
        objects = writer._add_object(pdf_dict(Nested=writer._add_object(nested)))
        root = pdf_dict(**{category: objects})
        if cycle:
            # Shared and self-referencing resources must be visited just once.
            resources[NameObject("/" + category)] = objects
        page[NameObject("/Resources")] = writer._add_object(root)
    else:
        page[NameObject("/Resources")] = resource_ref
    writer.write(path)
    writer.close()


@pytest.mark.parametrize("indirect", [False, True])
def test_font_dictionary_can_be_direct_or_indirect(tmp_path, indirect):
    path = tmp_path / "font.pdf"
    resource_pdf(path, embedded=True, indirect=indirect)
    assert verify_compilation(path, "") == {"total_pages": 1, "fonts_embedded": True}


@pytest.mark.parametrize("category", [None, "XObject", "Pattern"])
def test_unembedded_fonts_are_rejected_in_page_and_nested_resources(tmp_path, category):
    path = tmp_path / "unembedded.pdf"
    resource_pdf(path, embedded=False, category=category)
    with pytest.raises(ReaderError, match="A PDF font is not embedded"):
        verify_compilation(path, "")


@pytest.mark.parametrize("category", ["XObject", "Pattern"])
def test_embedded_fonts_in_shared_and_cyclic_resources_are_accepted(tmp_path, category):
    path = tmp_path / "recursive.pdf"
    resource_pdf(path, embedded=True, category=category, cycle=True)
    assert verify_compilation(path, "") == {"total_pages": 1, "fonts_embedded": True}
