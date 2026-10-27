# LoAgent gateway build: the dashboard is built from this branch's sources in a
# separate stage and bundled into the image, so the runtime serves the stripped
# WebUI instead of downloading the upstream one (see LOAGENT.md, "打包注意").
FROM node:24-bookworm-slim AS dashboard
WORKDIR /AstrBot/dashboard
RUN corepack enable && corepack prepare pnpm@11.28.5 --activate
ENV CI=true
COPY dashboard/package.json dashboard/pnpm-lock.yaml dashboard/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY dashboard/ ./
# vite.config.ts bundles the text-to-image runtime from the Python package.
COPY astrbot/core/utils/t2i/template/ /AstrBot/astrbot/core/utils/t2i/template/
COPY pyproject.toml /AstrBot/pyproject.toml
# assets/version must match the core version, or the runtime treats the bundle as
# stale and downloads the upstream WebUI.
RUN pnpm build \
    && mkdir -p dist/assets \
    && sed -n 's/^version = "\(.*\)"$/v\1/p' /AstrBot/pyproject.toml | head -n 1 > dist/assets/version \
    && test -s dist/assets/version \
    && test -f dist/index.html

FROM python:3.12-slim
WORKDIR /AstrBot

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    python3-dev \
    libffi-dev \
    libssl-dev \
    ca-certificates \
    bash \
    ffmpeg \
    libavcodec-extra \
    fonts-noto-cjk \
    curl \
    gnupg \
    git \
    ripgrep \
    && curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY . /AstrBot/
COPY --from=dashboard /AstrBot/dashboard/dist /AstrBot/astrbot/dashboard/dist

# Bootstrap pip from the hash-verified wheel before downloading other packages.
RUN python -m pip install --no-cache-dir \
    "pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70" \
    && python -m pip install --upgrade --no-cache-dir "uv>=0.13.4" \
    && echo "3.12" > .python-version \
    && uv lock \
    && uv export --format requirements.txt --output-file requirements.txt --frozen \
    && uv pip install -r requirements.txt --no-cache-dir --system \
    && uv pip install socksio uv pilk --no-cache-dir --system \
    && uv pip install --upgrade "certifi>=2026.10.19" "pip>=26.2.2" --no-cache-dir --system \
    && uv pip install -e . --no-deps --system \
    && touch /AstrBot/.astrbot

EXPOSE 6185

CMD ["python", "main.py"]
