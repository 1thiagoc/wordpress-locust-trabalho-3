<?php
/**
 * Instala o WordPress, se ainda nao estiver instalado, e publica os tres posts
 * do trabalho com os mesmos IDs usados na outra maquina: 5, 8 e 10.
 *
 * Uso, dentro do container wordpress1:
 *   php /tmp/publicar_posts.php /tmp/conteudo
 */

if ($argc < 2) {
    fwrite(STDERR, "Uso: php publicar_posts.php <pasta-com-os-arquivos>\n");
    exit(1);
}

$pasta = rtrim($argv[1], '/');
$imagem1 = $pasta . '/imagem-1mb.jpg';
$imagem300 = $pasta . '/imagem-300kb.jpg';
$texto = $pasta . '/texto-400kb.txt';

foreach (array($imagem1, $imagem300, $texto) as $arquivo) {
    if (!is_file($arquivo)) {
        fwrite(STDERR, "Arquivo ausente: $arquivo\n");
        exit(1);
    }
}

define('WP_INSTALLING', true);
require '/var/www/html/wp-load.php';
require_once ABSPATH . 'wp-admin/includes/upgrade.php';
require_once ABSPATH . 'wp-admin/includes/image.php';
require_once ABSPATH . 'wp-admin/includes/file.php';
require_once ABSPATH . 'wp-admin/includes/media.php';

if (!is_blog_installed()) {
    wp_install(
        'Testes de Carga',
        'admin',
        'admin@example.com',
        true,
        '',
        'admin123'
    );
}

update_option('blog_public', '1');
update_option('siteurl', 'http://localhost');
update_option('home', 'http://localhost');

function publicar_imagem($caminho, $post_id, $titulo) {
    $existente = get_post($post_id);
    if ($existente && $existente->post_type === 'post' && $existente->post_status === 'publish') {
        return (int) $post_id;
    }

    $bits = wp_upload_bits(basename($caminho), null, file_get_contents($caminho));
    if (!empty($bits['error'])) {
        fwrite(STDERR, "Falha no upload de $caminho: {$bits['error']}\n");
        exit(1);
    }

    $attachment_id = wp_insert_attachment(array(
        'post_mime_type' => 'image/jpeg',
        'post_title' => sanitize_file_name(basename($caminho)),
        'post_status' => 'inherit',
    ), $bits['file']);

    if (is_wp_error($attachment_id) || !$attachment_id) {
        fwrite(STDERR, "Falha ao criar anexo de $caminho\n");
        exit(1);
    }

    $meta = wp_generate_attachment_metadata($attachment_id, $bits['file']);
    wp_update_attachment_metadata($attachment_id, $meta);
    $url = wp_get_attachment_url($attachment_id);

    $resultado = wp_insert_post(array(
        'import_id' => $post_id,
        'post_title' => $titulo,
        'post_status' => 'publish',
        'post_type' => 'post',
        'post_content' => '<p><img src="' . esc_url($url) . '" alt="' . esc_attr($titulo) . '" /></p>',
    ), true);

    if (is_wp_error($resultado)) {
        fwrite(STDERR, $resultado->get_error_message() . "\n");
        exit(1);
    }

    return (int) $resultado;
}

function publicar_texto($caminho, $post_id, $titulo) {
    $existente = get_post($post_id);
    if ($existente && $existente->post_type === 'post' && $existente->post_status === 'publish') {
        return (int) $post_id;
    }

    $conteudo = file_get_contents($caminho);
    $resultado = wp_insert_post(array(
        'import_id' => $post_id,
        'post_title' => $titulo,
        'post_status' => 'publish',
        'post_type' => 'post',
        'post_content' => '<p>' . esc_html($conteudo) . '</p>',
    ), true);

    if (is_wp_error($resultado)) {
        fwrite(STDERR, $resultado->get_error_message() . "\n");
        exit(1);
    }

    return (int) $resultado;
}

$ids = array(
    'imagem_1mb' => publicar_imagem($imagem1, 5, 'Blog post com imagem de aproximadamente 1 MB'),
    'texto_400kb' => publicar_texto($texto, 8, 'Blog post com texto de aproximadamente 400 KB'),
    'imagem_300kb' => publicar_imagem($imagem300, 10, 'Blog post com imagem de aproximadamente 300 KB'),
);

echo json_encode($ids), "\n";
