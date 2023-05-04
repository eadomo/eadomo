import React, { useState, useRef, useLayoutEffect } from 'react';
import useAxios from "axios-hooks";
import Container from 'react-bootstrap/Container';
import Stack from 'react-bootstrap/Stack';
import Spinner from 'react-bootstrap/Spinner';
import ButtonGroup from 'react-bootstrap/ButtonGroup';
import ToggleButton from 'react-bootstrap/ToggleButton';
import 'moment-timezone';
import moment from 'moment';
import Moment from 'react-moment';
import ErrorMessage from './ErrorMessage.js'
import getBackendUrlBase from './backendUrl.js'

export default function UptimeGraph(props) {
    const myRef = useRef();

    const [container, ] = useState(props.container);
    const [type, ] = useState(props.type); // container, jmx or jmx/user_defined
    const [displayedInterval, setDisplayedInterval] = useState(24);

    const now = moment();
    const [numBins, setNumBins] = useState(48);
    const endTime = now;
    const startTime = now.clone().add(-displayedInterval, 'hour');

    useLayoutEffect(() => {
        const apprxNumBins = myRef.current.clientWidth / 20;
        const newNumBins = Math.max(24, Math.floor(apprxNumBins / 24) * 24);
        setNumBins(newNumBins);
    }, []);

    const backendUrl = container ? getBackendUrlBase() + type +'/'
        + container + '/status_timeseries?num_bins='+numBins+'&hours_back='+displayedInterval :
        getBackendUrlBase() + '/status_timeseries?num_bins='+numBins+'&hours_back='+displayedInterval;

    const [{ data, loading, error }] = useAxios(backendUrl)

    let readablePeriod = "";

    let cols = []

    if (loading) {
        readablePeriod =
            <div className="text-center">
                <Spinner animation="border" role="status" variant="primary">
                  <span className="visually-hidden">Loading...</span>
                </Spinner>
            </div>
    } else if (error) {
        return <ErrorMessage message={error.message}/>
    } else if (data) {
        const numPoints = data.length
        for (let i = 0; i < numPoints; i++) {
            const status = data[i]
            let color = 'blue';
            if (status === "nostat")
                color = 'darkgrey';
            else if (status === "allok")
                color = 'lightgreen'
            else if (status === "fatal")
                color = 'red';
            else if (status === "severe")
                color = 'orange';
            else if (status === "warning")
                color = 'yellow';
            cols[i] = color;
        }
        if (endTime === now) {
            readablePeriod = <div>Previous <Moment date={startTime} format="hh" durationFromNow/> hours</div>
        } else {
            readablePeriod = <div><Moment>{startTime}</Moment> - <Moment>{endTime}</Moment></div>
        }
    }

    function Bins(){
        if (!data)
            return "";

        return <div style={{width:"100%", display: "flex", justifyContent: "space-between"}}>{
            cols.map((x,idx) =>
                <span key={'graph'+idx} style={{
                    height: '70px',
                    width: '20px',
                    marginLeft: '5px',
                    marginRight: '5px',
                    borderColor: x,
                    borderWidth: '5px',
                    borderRadius: '10px',
                    borderStyle: 'solid',
                    backgroundColor: x }}/>

                )
        }</div>
    }

    const allowedIntervals = [
        24, 48, 72, 96, 120, 144, 168, 192, 216, 240
    ]

    return <Container ref={myRef}>
        <Stack direction="vertical" gap={3}>
            <Bins/>
            {readablePeriod}
            { true &&
            <ButtonGroup>
                { allowedIntervals.map((interval, idx) =>
                <ToggleButton key={container+'-'+interval} id={container+'-'+interval} type="radio"
                    variant="outline-primary" name={interval}
                    checked={displayedInterval === interval}
                    onChange={(e) => setDisplayedInterval(interval)}
                    >{interval}</ToggleButton>
                )}
            </ButtonGroup>
            }
        </Stack>
    </Container>

}
