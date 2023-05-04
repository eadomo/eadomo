import React, { useState } from 'react';
import Spinner from 'react-bootstrap/Spinner';
import useAxios from "axios-hooks";
import ReactJson from 'react-json-view'
import getBackendUrlBase from './backendUrl.js'

export default function RunTaskWindow(props) {
    const [url, ] = useState(props.url)
    const [title, ] = useState(props.title)

    console.log("task url:", url)

    const backendUrl = getBackendUrlBase() + url

    console.log(`loading task execution log from ${backendUrl}`)

    const axiosParams = { url: backendUrl, withCredentials: true };

    const [{ data, loading, error }] =
        useAxios(axiosParams)

    return <div>
        { loading &&
        <div className="text-center">
            <Spinner animation="border" role="status" variant="primary">
              <span className="visually-hidden">Loading...</span>
            </Spinner>
        </div>
        }
        { error &&
        <div>Error running task {title}: {error.message}</div>
        }
        { data &&
        <div className="shadow">
            <ReactJson src={data} displayDataTypes={false} quotesOnKeys={false}/>
        </div>
        }
   </div>
}
