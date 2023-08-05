using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class ServerPinger: MonoBehaviour
{
    public delegate void ZoneStateReceived(Dictionary<string, string> args, string myShipUuid);
    public static event ZoneStateReceived OnZoneStateReceived;

    public delegate void NewShipUuidReceived(string myShipUuid);
    public static event NewShipUuidReceived OnNewShipUuidReceived;

    private string currentShipUuid;
    private float lastPingTime = 0;
    

    // Start is called before the first frame update
    void Start()
    {
        StartCoroutine(HttpApi.NewPlayer(SetUuid));
    }

    private void SetUuid(Dictionary<string, string> args)
    {
        currentShipUuid = args["ship_uuid"];
        OnNewShipUuidReceived?.Invoke(currentShipUuid);
    }

    // Update is called once per frame
    void Update()
    {
        if (Time.time - lastPingTime > 1.5f)
        {
            lastPingTime = Time.time;
            StartCoroutine(HttpApi.ZoneReadPing("zone_0_0", ZoneDisplayCallback));
        }
    }

    void ZoneDisplayCallback(Dictionary<string, string> args)
    {
        OnZoneStateReceived?.Invoke(args, currentShipUuid);
    }
}
