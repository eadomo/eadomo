import React, { useState } from 'react';
import Spinner from 'react-bootstrap/Spinner';
import useAxios from "axios-hooks";
import FileDownload from 'js-file-download';
import Ansi from "ansi-to-react";
import getBackendUrlBase from './backendUrl.js'

export default function ActionWindow(props) {
    const [action, ] = useState(props.action);

    const backendUrl = getBackendUrlBase() + 'action/'
        + action.id + '/invoke'

    console.log(`loading action execution log from ${backendUrl}`)

    const axiosParams = { url: backendUrl, withCredentials: true };

    if (action.hasArtifacts) {
        axiosParams.responseType = 'blob'
    }
    const [{ data, loading, error }] =
        useAxios(axiosParams)

    if (action.hasArtifacts && data && !loading && !error) {
        FileDownload(data, 'artifacts.tar.gz');
    }

    return <div>
        { loading &&
        <div className="text-center">
            <Spinner animation="border" role="status" variant="primary">
              <span className="visually-hidden">Loading...</span>
            </Spinner>
        </div>
        }
        { error &&
        <div>Error: {error.message}</div>
        }
        { action.hasArtifacts && data &&
            <div>done, artifacts received</div>
        }
        { !action.hasArtifacts && data &&
        <div className="shadow" style={{ background: 'black', overflowY: 'auto', maxHeight: 'calc(100vh - 200px)' }}>
            <pre style={{ padding: '10px', textAlign: 'left', background: 'black', color: 'white' }}>
                <Ansi>{data}</Ansi>
            </pre>
        </div>
        }
   </div>
}
