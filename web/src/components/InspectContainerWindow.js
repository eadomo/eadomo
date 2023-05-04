import React, { useState, useRef } from 'react';
import Spinner from 'react-bootstrap/Spinner';
import Stack from 'react-bootstrap/Stack';
import * as Icon from 'react-bootstrap-icons';
import useAxios from "axios-hooks";
import ReactJson from 'react-json-view'
import ErrorMessage from './ErrorMessage.js'
import getBackendUrlBase from './backendUrl.js'

export default function InspectContainerWindow(props) {
    const [container, ] = useState(props.container);

    const topRef = useRef(null);
    const bottomRef = useRef(null);

    const backendUrl = getBackendUrlBase() + 'container/'
        + container + '/inspect'

    const [{ data: inspectData, loading: loadingData, error: errorData }] =
        useAxios({url: backendUrl, withCredentials: true})

    const scrollToTop = () => topRef.current.scrollIntoView()

    const scrollToBottom = () => bottomRef.current.scrollIntoView()

    return <div>
        { loadingData &&
            <div className="text-center">
                <Spinner nimation="border" role="status" variant="primary">
                  <span className="visually-hidden">Loading...</span>
                </Spinner>
            </div>
        }
        { errorData && <ErrorMessage message={errorData.message}/>
        }
        { !loadingData && inspectData &&
        <React.Fragment>
        <Stack direction="horizontal" gap={3}>
        <div className="shadow" style={{ width: "100%", overflowY: 'auto', maxHeight: 'calc(100vh - 200px)' }}>
            <div ref={topRef}/>
            <ReactJson src={inspectData} displayDataTypes={false} quotesOnKeys={false}/>
            <div ref={bottomRef}/>
        </div>
        <Stack gap={3}>
            <div onClick={scrollToTop} style={{ cursor: "pointer"}}><Icon.ArrowUp/></div>
            <div onClick={scrollToBottom} style={{ cursor: "pointer"}}><Icon.ArrowDown/></div>
        </Stack>
        </Stack>
        </React.Fragment> }
    </div>
}