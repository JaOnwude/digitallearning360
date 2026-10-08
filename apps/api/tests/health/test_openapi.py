from fastapi import FastAPI


async def test_schema_names_are_unique(app_instance: FastAPI) -> None:
    """Two Pydantic models with the same name get mangled names (e.g. `app__fees__...`) in
    OpenAPI, which silently renames types in the generated web client. Give them distinct names."""
    names = app_instance.openapi()["components"]["schemas"]
    mangled = sorted(n for n in names if "__" in n)
    assert not mangled, f"rename these duplicated schema names: {mangled}"
