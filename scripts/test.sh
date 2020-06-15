#!/bin/bash

docker-compose build test-library
docker-compose run --rm test-library test
