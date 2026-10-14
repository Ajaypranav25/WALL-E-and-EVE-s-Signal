"""HTTP API for the visualizer: list configs, run missions, run benchmarks.

Every response uses the envelope ``{"success", "data", "error"}``.
"""

import os
import re
import threading
import time
import uuid
from collections import OrderedDict, defaultdict, deque
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError, model_validator

from .benchmark import MAX_BENCH_MISSIONS, run_benchmark
from .config import MissionConfig, load_config
from .mission import run_mission

CONFIG_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
CONFIG_SUFFIXES = (".yaml", ".yml", ".json")
RUN_CACHE_SIZE = 20
API_BENCH_LIMIT = 100  # keep synchronous requests short; the CLI has no such cap
API_MAX_TIME_LIMIT = 1000
API_MAX_GRID = 40
MAX_CONCURRENT_JOBS = 2
LLM_ENV_FLAG = "SIGNAL_API_ALLOW_LLM"  # the LLM planner spends the server's API key, so it is opt-in
PlannerName = Literal["classical", "greedy", "llm"]


def default_config_dir() -> Path:
    env = os.environ.get("SIGNAL_CONFIG_DIR")
    # Configs live inside the backend so they ship in its deployment bundle.
    return Path(env) if env else Path(__file__).resolve().parents[1] / "configs"


class RateLimiter:
    """Sliding-window limit per client and route bucket."""

    def __init__(self, limit: int, window_s: float = 60.0):
        self.limit, self.window = limit, window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def __call__(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                raise HTTPException(status_code=429, detail="Too many requests; try again in a minute.")
            hits.append(now)


class MissionRequest(BaseModel):
    config_name: str | None = Field(None, pattern=CONFIG_NAME.pattern)
    config: MissionConfig | None = None
    seed: int | None = Field(None, ge=0, le=2**31 - 1)
    planner: PlannerName = "classical"

    @model_validator(mode="after")
    def _exactly_one_source(self) -> "MissionRequest":
        if sum(x is not None for x in (self.config_name, self.config)) > 1:
            raise ValueError("give config_name or config, not both")
        return self


class BenchRequest(BaseModel):
    n: int = Field(20, ge=1, le=min(API_BENCH_LIMIT, MAX_BENCH_MISSIONS))
    seed: int = Field(0, ge=0, le=2**31 - 1)
    planners: list[PlannerName] = Field(default_factory=lambda: ["classical", "greedy"], min_length=1, max_length=3)


def check_api_limits(cfg: MissionConfig) -> None:
    """Inline configs share server CPU and memory, so the API is stricter than the CLI."""
    width = len(cfg.map.layout[0]) if cfg.map.layout else cfg.map.width
    height = len(cfg.map.layout) if cfg.map.layout else cfg.map.height
    if width > API_MAX_GRID or height > API_MAX_GRID:
        raise HTTPException(422, f"Maps over {API_MAX_GRID}x{API_MAX_GRID} are CLI-only.")
    if cfg.resources.time_limit > API_MAX_TIME_LIMIT:
        raise HTTPException(422, f"time_limit over {API_MAX_TIME_LIMIT} is CLI-only.")


def llm_allowed() -> bool:
    return os.environ.get(LLM_ENV_FLAG, "").lower() in {"1", "true", "yes"}


def ok(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}


def create_app(config_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="WALL-E and EVE's Signal", version="0.1.0")
    configs = config_dir or default_config_dir()
    runs: OrderedDict[str, dict[str, Any]] = OrderedDict()
    runs_lock = threading.Lock()
    mission_limit = RateLimiter(30)
    bench_limit = RateLimiter(4)
    jobs = threading.BoundedSemaphore(MAX_CONCURRENT_JOBS)

    def run_job(fn):
        if not jobs.acquire(blocking=False):
            raise HTTPException(429, "The simulator is busy with other missions; try again shortly.")
        try:
            return fn()
        finally:
            jobs.release()

    def require_llm_allowed(planners) -> None:
        if "llm" in planners and not llm_allowed():
            raise HTTPException(403, f"The Claude planner is disabled on this server. Set {LLM_ENV_FLAG}=1 to enable it.")

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"success": False, "data": None, "error": str(exc.detail)})

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {"msg": "invalid request"}
        where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        return JSONResponse(status_code=422, content={"success": False, "data": None, "error": f"{where}: {first['msg']}".strip(": ")})

    def find_config(name: str) -> Path:
        if not CONFIG_NAME.match(name):
            raise HTTPException(400, "Invalid config name.")
        for suffix in CONFIG_SUFFIXES:
            path = configs / f"{name}{suffix}"
            if path.is_file():
                return path
        raise HTTPException(404, f"No config named {name!r}.")

    def load_named(name: str) -> MissionConfig:
        try:
            return load_config(find_config(name))
        except (ValueError, ValidationError) as exc:
            raise HTTPException(422, f"Config {name!r} is invalid: {exc}") from exc

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return ok({"status": "ok"})

    @app.get("/api/configs")
    def list_configs() -> dict[str, Any]:
        items = []
        for path in sorted(configs.glob("*")):
            if path.suffix in CONFIG_SUFFIXES and CONFIG_NAME.match(path.stem):
                try:
                    cfg = load_config(path)
                    items.append({"name": path.stem, "title": cfg.name, "description": cfg.description, "format": path.suffix[1:]})
                except ValueError as exc:  # pydantic's ValidationError is a ValueError
                    items.append({"name": path.stem, "title": path.stem, "description": "", "format": path.suffix[1:], "error": str(exc).splitlines()[0]})
        return ok(items)

    @app.get("/api/configs/{name}")
    def get_config(name: str) -> dict[str, Any]:
        path = find_config(name)
        return ok({"name": name, "format": path.suffix[1:], "source": path.read_text(encoding="utf-8"), "config": load_named(name).model_dump(mode="json")})

    @app.post("/api/missions", dependencies=[Depends(mission_limit)])
    def create_mission(req: MissionRequest) -> dict[str, Any]:
        if req.config is not None:
            cfg = req.config
        elif req.config_name:
            cfg = load_named(req.config_name)
        else:
            cfg = MissionConfig(name="Random mission", seed=req.seed or 0, decoy_count=1)
        if req.seed is not None and req.config_name:
            cfg = cfg.model_copy(update={"seed": req.seed})
        check_api_limits(cfg)
        require_llm_allowed([req.planner])
        try:
            result = run_job(lambda: run_mission(cfg, req.planner))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        run_id = uuid.uuid4().hex[:12]
        bundle = {"id": run_id, **result.bundle()}
        with runs_lock:
            runs[run_id] = bundle
            while len(runs) > RUN_CACHE_SIZE:
                runs.popitem(last=False)
        return ok(bundle)

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        with runs_lock:
            bundle = runs.get(run_id)
        if bundle is None:
            raise HTTPException(404, "Run not found (only the most recent runs are kept).")
        return ok(bundle)

    @app.post("/api/benchmark", dependencies=[Depends(bench_limit)])
    def benchmark(req: BenchRequest) -> dict[str, Any]:
        require_llm_allowed(req.planners)
        try:
            return ok(run_job(lambda: run_benchmark(req.n, req.seed, tuple(dict.fromkeys(req.planners)))))
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc

    return app


app = create_app()
