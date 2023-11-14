import React, { useState, useRef } from 'react';
import Spinner from 'react-bootstrap/Spinner';
import Stack from 'react-bootstrap/Stack';
import Ansi from "ansi-to-react";
import * as Icon from 'react-bootstrap-icons';
import useAxios from "axios-hooks";
import ErrorMessage from './ErrorMessage.js'
import getBackendUrlBase from './backendUrl.js'

export default function LogWindow(props) {
    const [container, ] = useState(props.container);

    const topRef = useRef(null);
    const bottomRef = useRef(null);

    const backendUrl = getBackendUrlBase() + 'container/'
        + container + '/log'

    const [{ data: log, loading: loadingLog, error: errorLog }, executeFetch] =
        useAxios({url: backendUrl, withCredentials: true})

    function refresh() {
        executeFetch();
    }

    const scrollToTop = () => topRef.current.scrollIntoView()

    const scrollToBottom = () => bottomRef.current.scrollIntoView()

    return <div>
        { loadingLog && !log &&
            <div className="text-center">
                <Spinner animation="border" role="status" variant="primary">
                  <span className="visually-hidden">Loading...</span>
                </Spinner>
            </div>
        }
        { errorLog && <ErrorMessage message={errorLog.message}/>
        }
        { log &&
        <React.Fragment>
        <Stack direction="horizontal" gap={3}>
        <div className="shadow" style={{ background: 'black', overflowY: 'auto', maxHeight: 'calc(100vh - 200px)' }}>
            <div ref={topRef}/>
            <pre style={{ padding: '10px', textAlign: 'left', background: 'black', color: 'white' }}>
                {log.truncated && "...\n"}
                <Ansi>{log.log}</Ansi>
            </pre>
            <div ref={bottomRef}/>
        </div>
        <Stack gap={3}>
            <div onClick={scrollToTop} style={{ cursor: "pointer"}}><Icon.ArrowUp/></div>
            <div onClick={scrollToBottom} style={{ cursor: "pointer"}}><Icon.ArrowDown/></div>
        </Stack>
        </Stack>
        </React.Fragment> }
        <Stack direction="horizontal" gap={3}>
        { log &&
        <div style={{ width: "100%" }}>
            <a href={getBackendUrlBase() + 'container/' + container + '/full-log'}>Download full log</a>
        </div>
        }
        { !loadingLog && log &&
        <div onClick={refresh} style={{ cursor: "pointer"}}><Icon.Repeat/></div>
        }
        </Stack>
    </div>
}