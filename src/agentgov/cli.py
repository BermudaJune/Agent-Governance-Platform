from __future__ import annotations

from pathlib import Path

import typer
import uvicorn

from agentgov.config.loader import load_config
from agentgov.app import create_app
from agentgov.storage.db import init_db
from agentgov.testing.qualification_scenario import run_qualification

app = typer.Typer(help="Agent governance platform CLI")
config_app = typer.Typer(help="Configuration commands")
db_app = typer.Typer(help="Database commands")
qualification_app = typer.Typer(help="Qualification scenario commands")
app.add_typer(config_app, name="config")
app.add_typer(db_app, name="db")
app.add_typer(qualification_app, name="qualification")


@config_app.command("validate")
def validate_config(path: Path) -> None:
    cfg = load_config(path)
    typer.echo(
        f"valid config: providers={len(cfg.providers)} agents={len(cfg.agents)} teams={len(cfg.teams)}"
    )


@db_app.command("init")
def init_database(
    database: str = typer.Option("sqlite:///./data/agentgov.db", "--database")
) -> None:
    init_db(database)
    typer.echo(f"database initialized: {database}")


@app.command("api")
def run_api(
    host: str = "127.0.0.1",
    port: int = 8000,
    database: str = "sqlite:///./data/agentgov.db",
    config: Path = Path("config/examples/local.scripted.yaml"),
) -> None:
    api = create_app(database=database, config_path=str(config))
    uvicorn.run(api, host=host, port=port)


@qualification_app.command("run")
def qualification_run(
    config: Path = typer.Option(..., "--config"),
    database: str = typer.Option("sqlite:///./data/agentgov.db", "--database"),
) -> None:
    result = run_qualification(config, database)
    typer.echo(result.to_json())


if __name__ == "__main__":
    app()
