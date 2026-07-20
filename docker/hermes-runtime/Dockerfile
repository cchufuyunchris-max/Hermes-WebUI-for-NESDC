FROM python:3.11-slim@sha256:ae52c5bef62a6bdd42cd1e8dffef86b9cd284bde9427da79839de7a4b983e7ca

ENV PIP_DEFAULT_TIMEOUT=180 \
    PIP_RETRIES=10

RUN useradd --create-home --home-dir /home/hermes --shell /bin/sh hermes

WORKDIR /home/hermes

COPY apps/webui/requirements.txt /tmp/hermes-webui-requirements.txt
COPY vendor/hermes-agent/ /home/hermes/agent/
RUN python3 -m pip install --no-cache-dir -r /tmp/hermes-webui-requirements.txt
RUN python3 -m pip install --no-cache-dir -e /home/hermes/agent

ENV APP_ENV=production \
    PORT=8080 \
    HERMES_WEBUI_HOST=0.0.0.0 \
    HERMES_WEBUI_PORT=8080 \
    HERMES_WEBUI_STATE_DIR=/home/hermes/data/webui \
    HERMES_WEBUI_DEFAULT_WORKSPACE=/home/hermes/data/workspace \
    HERMES_WEBUI_AGENT_DIR=/home/hermes/agent \
    HERMES_WEBUI_ONBOARDING_OPEN=1 \
    HERMES_WEBUI_DEFAULT_THEME=light \
    HERMES_WEBUI_DEFAULT_LANGUAGE=zh \
    HERMES_HOME=/home/hermes/data/hermes \
    HERMES_DATA_DIR=/home/hermes/data \
    HERMES_USER_SKILLS_DIR=/home/hermes/data/skills \
    HERMES_SKILL_STATE_FILE=/home/hermes/data/skill-state.json \
    HERMES_PROVISIONED_SKILLS_DIR=/home/hermes/provisioned-skills \
    HERMES_AUTO_INSTALL_RECOMMENDED_SKILLS=false \
    PROJECT_SKILLS_UPDATE_POLICY=manual

COPY docker/hermes-runtime/skill-init.py /home/hermes/runtime/skill-init.py
COPY docker/hermes-runtime/policy-init.py /home/hermes/runtime/policy-init.py
COPY docker/hermes-runtime/entrypoint.sh /home/hermes/runtime/entrypoint.sh
COPY docker/hermes-runtime/placeholder-server.py /home/hermes/runtime/placeholder-server.py
COPY apps/webui/ /home/hermes/app/
COPY skills/ /home/hermes/provisioned-skills/

RUN chmod +x /home/hermes/runtime/entrypoint.sh /home/hermes/runtime/skill-init.py \
    && chmod +x /home/hermes/runtime/policy-init.py \
    && chmod +x /home/hermes/runtime/placeholder-server.py \
    && touch /.within_container \
    && mkdir -p /home/hermes/data /home/hermes/builtin-skills \
    && chown -R hermes:hermes /home/hermes

USER hermes

EXPOSE 8080

CMD ["/home/hermes/runtime/entrypoint.sh"]
