# Changelog

## [0.3.0](https://github.com/ffoerster/ee-ark/compare/v0.2.0...v0.3.0) (2026-04-20)


### Features

* add custom admin theme and integrate Whitenoise for static file handling ([a0434aa](https://github.com/ffoerster/ee-ark/commit/a0434aa5d6c5486cad208bbcc2ec909760d91d2f))
* add healthcheck configuration for arklet services in Docker Compose ([58a4bf6](https://github.com/ffoerster/ee-ark/commit/58a4bf64f81aab7538c65101596e7dd478d2696a))
* add tombstone support to ARK model and update related views, forms, and templates ([1d167c4](https://github.com/ffoerster/ee-ark/commit/1d167c40476597390de83971b6fdc5165a5ffabe))
* enhance ARK API with improved request handling, tombstone support, and history retrieval ([069dc48](https://github.com/ffoerster/ee-ark/commit/069dc486ddac9d7f01ae9d8d468b42400a615c8f))
* enhance ArkAdmin with additional list display, filtering, and readonly fields; update migration index formatting; improve JSON response formatting in history_ark view ([d5f9a38](https://github.com/ffoerster/ee-ark/commit/d5f9a38ebfa6154eed2b60f4e4b33692b337f98b))
* enhance error handling in ARK endpoints with consistent JSON responses and request IDs ([ccc3cac](https://github.com/ffoerster/ee-ark/commit/ccc3cacce0be8291010e61ea47a13031aa196e19))
* implement ARK event logging and history retrieval endpoint ([9f821c5](https://github.com/ffoerster/ee-ark/commit/9f821c5ad4a85995abbb99215159237591424e27))


### Bug Fixes

* format staticfiles storage configuration for readability ([f670445](https://github.com/ffoerster/ee-ark/commit/f6704458351f23fe9974bef0bd36c3b7368f82d2))
* update healthcheck URLs in docker-compose to use 127.0.0.1 ([0488162](https://github.com/ffoerster/ee-ark/commit/04881622b5c9f4d635b3f26b83200efc1ef316f3))

## [0.2.0](https://github.com/ffoerster/ee-ark/compare/v0.1.0...v0.2.0) (2026-04-20)


### Features

* enhance ARK CLI with rich console output and refactor request handling ([1a34401](https://github.com/ffoerster/ee-ark/commit/1a34401ccda3453c8a50f8804d6d7cf768ec0372))
* upgrade Python version to 3.12, add request logging middleware, and implement rate limiting ([288e312](https://github.com/ffoerster/ee-ark/commit/288e312c5a0db21dc9c1f34ac4e43205cd5626b6))


### Bug Fixes

* update dependencies in poetry.lock and remove obsolete packages ([444b84e](https://github.com/ffoerster/ee-ark/commit/444b84e94fde55758b79b590be39adbadb3368a5))
* update requests package version to 2.32.4 ([18830a3](https://github.com/ffoerster/ee-ark/commit/18830a316e69f590db2792a92b6c775505d362b8))

## 0.1.0 (2026-04-20)


### Features

* Add docker healthcheck route ([23eaa06](https://github.com/ffoerster/ee-ark/commit/23eaa0636b4299a569921341b9de18bb4a389858))
* Upgrade to Python 3.10 ([13846e8](https://github.com/ffoerster/ee-ark/commit/13846e8d1b8cf4d4dcffef077d03c8d4d7a367b5))


### Bug Fixes

* Refactor bandit errors ([4b1b266](https://github.com/ffoerster/ee-ark/commit/4b1b26670451595f455d8a626427742a8ce1ddac))
* update click version to 8.2.1 in requirements.txt ([8525513](https://github.com/ffoerster/ee-ark/commit/85255131cb6fb067a7092f431d2a0047a3af47e8))
* Update lint job ([1526146](https://github.com/ffoerster/ee-ark/commit/1526146cb1c2f48914ab1bcd14bc93e67b0c8400))
* update psycopg2-binary version to 2.9.9 and change base image to python:3.10-slim-bullseye ([b167026](https://github.com/ffoerster/ee-ark/commit/b1670262e1eee61dfa93294298ef17d6e1e49915))
