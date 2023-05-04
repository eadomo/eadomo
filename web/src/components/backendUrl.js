
export default function getBackendUrlBase() {
    let backend_url_base = window.location.href;
    backend_url_base = backend_url_base.substring(0, backend_url_base.lastIndexOf('/'));
    if (!backend_url_base.endsWith('/'))
        backend_url_base += '/';
    if (process.env.REACT_APP_OVERRIDE_BACKEND_PORT)
        backend_url_base = backend_url_base.replace(window.location.port, process.env.REACT_APP_OVERRIDE_BACKEND_PORT)

    return backend_url_base;
}
