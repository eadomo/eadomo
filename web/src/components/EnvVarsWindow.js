import React, { useState, useRef } from 'react';
import Spinner from 'react-bootstrap/Spinner';
import Stack from 'react-bootstrap/Stack';
import Table from 'react-bootstrap/Table';
import * as Icon from 'react-bootstrap-icons';
import useAxios from "axios-hooks";
import ErrorMessage from './ErrorMessage.js'
import getBackendUrlBase from './backendUrl.js'

export default function EnvVarsWindow(props) {
    const [container, ] = useState(props.container);

    const topRef = useRef(null);
    const bottomRef = useRef(null);

    const backendUrl = getBackendUrlBase() + 'container/'
        + container + '/env'

    const [{ data: envVars, loading: loadingEnv, error: errorEnv }] =
        useAxios({url: backendUrl, withCredentials: true})

    const scrollToTop = () => topRef.current.scrollIntoView()

    const scrollToBottom = () => bottomRef.current.scrollIntoView()

    const getEnvVarName = (x) => {
        const eqPos = x.indexOf('=')
        return (eqPos !== -1) ? x.substr(0, eqPos) : x
    }

    const getEnvVarValue = (x) => {
        const eqPos = x.indexOf('=')
        return (eqPos !== -1) ? x.substr(eqPos+1) : ''
    }

    if (envVars)
        envVars.sort((a, b) => getEnvVarName(a).localeCompare(getEnvVarName(b)))

    return <div>
        { loadingEnv &&
            <div className="text-center">
                <Spinner nimation="border" role="status" variant="primary">
                  <span className="visually-hidden">Loading...</span>
                </Spinner>
            </div>
        }
        { errorEnv && <ErrorMessage message={errorEnv.message}/>
        }
        { !loadingEnv && envVars &&
        <React.Fragment>
        <Stack direction="horizontal" gap={3}>
        <div className="shadow" style={{ width: "100%", overflowY: 'auto', maxHeight: 'calc(100vh - 200px)' }}>
            <div ref={topRef}/>
            <Table striped bordered hover style={{width: "100%"}}>
                <thead>
                    <tr>
                        <th scope="col">name</th>
                        <th scope="col">value</th>
                    </tr>
                </thead>
                <tbody>
                    {envVars.map((x,idx) =>
                        <tr key={"var-"+idx}>
                            <td className="small">{getEnvVarName(x)}</td>
                            <td className="small">{getEnvVarValue(x)}</td>
                        </tr>
                    )}
                </tbody>
            </Table>
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