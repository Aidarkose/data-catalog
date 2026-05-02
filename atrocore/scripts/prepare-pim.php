<?php
// Адаптация официального prepare-pim.php — host берём из ARG/ENV,
// чтобы AtroCore смотрел на omega3-postgres, а не на дефолтный 'db'.

if (empty($argv[1]) || empty($argv[2]) || empty($argv[3])) {
    exit("DB credentials are not set, skipping");
}

chdir(dirname(__FILE__));
set_include_path(dirname(__FILE__));

require_once 'vendor/autoload.php';

$app = new \Atro\Core\Application();

$dbHost = getenv('DB_HOST') ?: 'omega3-postgres';
$dbPort = getenv('DB_PORT') ?: '5432';

$config = $app->getContainer()->get('config');
$config->set('database', [
    'driver' => 'pdo_pgsql',
    'host' => $dbHost,
    'port' => $dbPort,
    'charset' => 'utf8',
    'dbname' => $argv[3],
    'user' => $argv[1],
    'password' => $argv[2],
]);
$config->set('useChromeNoSandbox', true);
$config->save();
