import React, { useState } from 'react';
import useAxios from "axios-hooks";
import Spinner from 'react-bootstrap/Spinner';
import Container from 'react-bootstrap/Container';
import { Line } from "react-chartjs-2";
import "chartjs-adapter-moment";
import ErrorMessage from './ErrorMessage.js'
import getBackendUrlBase from './backendUrl.js'

import {
  Chart as ChartJS,
  TimeScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
} from "chart.js";

ChartJS.register(
  TimeScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

export default function TimeseriesPlot(props) {
    const [container, ] = useState(props.container);
    const [parameter, ] = useState(props.parameter);
    const [plotName, ] = useState(props.plotName);
    const [convFunc, ] = useState((x) => props.convFunc);
    const [type, ] = useState(props.type); // container, jmx or jmx/user_defined

    const backendUrl = getBackendUrlBase() + type + '/'
        + encodeURIComponent(container) + '/' + encodeURIComponent(parameter)

    console.log(`loading timeseries from ${backendUrl}`)

    const [{ data, loading, error }] = useAxios(backendUrl)

    let values = []

    if (data) {
        const numPoints = data.length
        values = []
        const convFuncAct = convFunc ? convFunc : x => x
        for (let i = 0; i < numPoints; i++) {
            const x = data[i].timestamp
            const y = data[i].status[container].stats ?
                data[i].status[container].stats[parameter] : undefined;

            if (x != null && y != null)
                values.push({ x: x, y: convFuncAct(y)})
        }
    }

    const options = {
        response: true,
        scales: {
            x: {
                type: "time",
                time: {
                    unit: "minute"
                }
            }
        }
    }

    const plotData = {
        datasets: [
        {
            label: plotName ? plotName : parameter,
            data: values
        }
        ]
    };

    return <Container>
        { loading &&
            <div className="text-center">
                <Spinner animation="border" role="status" variant="primary">
                  <span className="visually-hidden">Loading...</span>
                </Spinner>
            </div>
        }
        { error && <ErrorMessage message={error.message}/>
        }
        { data &&
        <Line options={options} data={plotData} />
        }
        </Container>
}