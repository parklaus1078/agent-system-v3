# Control Tower — Docker workflow helpers (see docker-compose*.yml).
#
#   make up      build + start (detached), then prune the <none> images the rebuild orphaned
#   make dev     hot-reload stack (Compose Watch) — edit ./api or ./web, containers live-update
#   make down    stop + remove containers/networks (keeps images + named volumes)
#   make logs    follow all service logs
#   make prune   remove ALL dangling (<none>) images on this host
#   make clean   down + remove THIS project's built images + prune dangling (keeps db data)
#   make nuke    clean + DROP volumes (WARNING: deletes the Postgres data + project workspace)
#
# Why `make up` prunes: `docker compose up --build` re-tags the freshly built api/web images,
# which UNTAGS the previous ones -> they linger as dangling `<none>` images. `down` never
# removes images, so every down/up --build cycle leaves another pair. Pruning after the build
# clears exactly those orphans (prune only ever removes untagged, unreferenced images).

COMPOSE ?= docker compose
DEV      := $(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml

.PHONY: up down restart logs dev prune clean nuke

up:
	$(COMPOSE) up -d --build
	-docker image prune -f   # drop the now-dangling <none> images the rebuild left behind

down:
	$(COMPOSE) down

restart: down up

logs:
	$(COMPOSE) logs -f

dev:
	$(DEV) watch

prune:
	docker image prune -f

clean:
	$(COMPOSE) down --rmi local
	-docker image prune -f

nuke:
	$(COMPOSE) down -v --rmi local
	-docker image prune -f
