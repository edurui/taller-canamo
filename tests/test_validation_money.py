import pytest
from decimal import Decimal
from taller.errors import AppError
from taller.money import calculate, decimal, cents
from taller.validation import normalized, plate, valid_tax_id, valid_iban, iso_date, aware_date, clean_text

@pytest.mark.parametrize("source,expected",[("  Jos\u00e9  P\u00e9rez ","jose perez"),(None,""),("CA\u00d1AMO","canamo")])
def test_normalization(source,expected):
    assert normalized(source)==expected

@pytest.mark.parametrize("source",["0540-BZD","0540 bzd","0540BzD"])
def test_plate_normalization(source):
    assert plate(source)=="0540BZD"

@pytest.mark.parametrize("value",["12345678Z","X1234567L","Y1234567X","Z1234567R","B99286320"])
def test_valid_tax_checksum(value):
    assert valid_tax_id(value)

@pytest.mark.parametrize("value",["12345678A","X1234567A","B99286321","","hello",None])
def test_invalid_tax_checksum(value):
    assert not valid_tax_id(value)

def test_iban_checksum():
    assert valid_iban("ES91 2100 0418 4502 0005 1332")
    assert not valid_iban("ES92 2100 0418 4502 0005 1332")

def test_date_validation():
    assert iso_date("2024-02-29")=="2024-02-29"
    with pytest.raises(AppError):iso_date("2026-02-29")
    with pytest.raises(AppError):iso_date("2026-2-1")
    with pytest.raises(AppError):aware_date("2026-09-07T12:00:00")
    assert aware_date("2026-09-07T12:00:00Z").utcoffset().total_seconds()==0

def test_text_limits():
    with pytest.raises(AppError):clean_text({"name":""},"name",10,True)
    with pytest.raises(AppError):clean_text({"name":"ab\x00c"},"name")
    with pytest.raises(AppError):clean_text({"name":12},"name")
    assert clean_text({"name":" Ana "},"name")=="Ana"

@pytest.mark.parametrize("value",[1.2,True,None,"NaN","Infinity","1.23456","100000000"])
def test_reject_unsafe_decimal(value):
    with pytest.raises(AppError):decimal(value)

def test_invoice_reference_totals():
    result=calculate([{"description":"Material", "quantity":"1", "unit_price":"434.41"},
                      {"description":"Trabajo", "quantity":"1", "unit_price":"336.00"}])
    assert (result["base_cents"],result["tax_cents"],result["total_cents"])==(77041,16179,93220)

def test_grouped_tax_rounding():
    result=calculate([{"description":"A","unit_price":"0.03"},{"description":"B","unit_price":"0.03"}])
    assert result["base_cents"]==6 and result["tax_cents"]==1

def test_discount_and_decimal_comma():
    result=calculate([{"description":"A","quantity":"2","unit_price":"10,50","discount":"10"}])
    assert result["base_cents"]==1890 and result["total_cents"]==2287

def test_rectification_negative_totals():
    line={"description":"Devolucion","quantity":"-1","unit_price":"100"}
    with pytest.raises(AppError):calculate([line])
    assert calculate([line],corrective=True)["total_cents"]==-12100

@pytest.mark.parametrize("line",[{}, {"description":"A","quantity":"0"}, {"description":"A","discount":"101"},
    {"description":"A","tax_rate":"15"}, {"description":"A","tax_kind":"E1","tax_rate":"0"}])
def test_invalid_lines(line):
    with pytest.raises(AppError):calculate([line])

def test_exempt_requires_explicit_reason():
    result=calculate([{"description":"A","unit_price":"10","tax_kind":"E1","tax_rate":"0","tax_reason":"Caso ficticio"}])
    assert result["tax_cents"]==0


def test_non_object_invoice_line_rejected():
    with pytest.raises(AppError):calculate(["not-a-line"])
