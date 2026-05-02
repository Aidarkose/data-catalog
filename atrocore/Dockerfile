# ============================================================
# AtroCore (RDM/MDM) для OMEGA-3
#   - PHP 8.4 + Apache + Composer
#   - Skeleton клонируется из gitlab.atrocore.com на этапе билда
#   - data/config.php после билда смотрит на omega3-postgres
# Адаптация официального .docker/php/Dockerfile
# (https://gitlab.atrocore.com/atrocore/docker)
# ============================================================
FROM php:8.4-apache-bookworm

LABEL maintainer="OMEGA-3 / Dauren Aidarkhanov"

ARG SKELETON_VARIANT=atrocore
ARG STABILITY=stable
ARG DOMAIN=localhost
ARG DB_NAME=atrocore_db
ARG DB_USER=atrocore
ARG DB_PASSWORD=atrocore_secret_2026
ARG DB_HOST=omega3-postgres
ARG DB_PORT=5432

ENV DB_HOST=${DB_HOST} \
    DB_PORT=${DB_PORT} \
    PRODUCTION_DOMAIN=${DOMAIN}

RUN mv "$PHP_INI_DIR/php.ini-production" "$PHP_INI_DIR/php.ini"  \
    && printf "post_max_size = 20M\nupload_max_filesize = 20M\nmax_execution_time = 180\nmax_input_time = 180\nmemory_limit = 256M" >> "$PHP_INI_DIR/php.ini" \
    && apt-get update && apt-get install -y \
        git \
        cron \
        postgresql-client \
        zip unzip \
        build-essential \
        locales \
        libcurl4 \
        libcurl4-openssl-dev \
        libsodium-dev \
        libfreetype-dev \
        libjpeg62-turbo-dev \
        libpng-dev \
        libpq-dev \
        libavif-dev \
        libattr1-dev \
        libonig-dev \
        libzip-dev \
        zlib1g-dev \
        libmagickwand-dev \
        libldap2-dev \
        libldap-common \
    && docker-php-ext-configure gd --with-freetype --with-jpeg --with-avif \
    && docker-php-ext-install -j$(nproc) mbstring curl gd xml zip pdo_pgsql exif ftp ldap sockets \
    && pecl install xattr imagick \
    && docker-php-ext-enable xattr imagick \
    && a2enmod rewrite && a2dissite 000-default \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /var/www

COPY scripts /var/www/scripts

# Клонируем skeleton + composer install + пишем data/config.php с DB_HOST=omega3-postgres
RUN chmod +x scripts/*.sh && mkdir -p /var/spool/cron/crontabs/ \
    && /bin/bash ./scripts/prepare-pim.sh "${SKELETON_VARIANT}" "${STABILITY}" "${DOMAIN}" "${DB_USER}" "${DB_PASSWORD}" "${DB_NAME}" \
    && chown www-data:crontab /var/spool/cron/crontabs/www-data \
    && chmod 600 /var/spool/cron/crontabs/www-data \
    && rm -rf scripts && mkdir -p /var/www/.cache && chown www-data:www-data /var/www/.cache

COPY startup.sh /startup.sh
RUN chmod +x /startup.sh

EXPOSE 80
CMD ["/startup.sh"]
