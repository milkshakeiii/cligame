using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class Testing : MonoBehaviour
{
    private string uuid;

    // Start is called before the first frame update
    void Start()
    {
        StartCoroutine(HttpApi.NewPlayer(SetUuid));
    }

    private void SetUuid(Dictionary<string, string> args)
    {
        uuid = args["ship_uuid"];
    }

    // Update is called once per frame
    void Update()
    {
        if (uuid != null)
        {
            StartCoroutine(HttpApi.ZoneReadPing("zone_0_0", HttpApi.PrintCallback));
            uuid = null;
        }
    }
}
