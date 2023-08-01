using Newtonsoft.Json;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;

public static class HttpApi
{
    const string BASE_URL = "http://127.0.0.1:5001/functions-project-98551/us-central1/";

    public static void PrintCallback(Dictionary<string, string> args)
    {
        Debug.Log("Callback called with args:");
        foreach (var arg in args)
        {
            Debug.Log($"{arg.Key}: {arg.Value}");
        }
    }

    public static IEnumerator NewPlayer(System.Action<Dictionary<string, string>> callback)
    {
        Dictionary<string, string> args = new Dictionary<string, string>();
        args.Add("player_name", "Player1");
        args.Add("ship", "{\"position\":\"0,0\",\"facing\":\"N\"}");
        args.Add("spawn_location", "0,0");
        yield return Get("new_player", args, callback);
    }

    //http://127.0.0.1:5001/functions-project-98551/us-central1/zone_read_ping?zone_name=zone_0_0
    public static IEnumerator ZoneReadPing(string zone_name, System.Action<Dictionary<string, string>> callback)
    {
        Dictionary<string, string> args = new Dictionary<string, string>();
        args.Add("zone_name", zone_name);
        yield return Get("zone_read_ping", args, callback);
    }

    public static IEnumerator Get(string endpoint, Dictionary<string, string> args, System.Action<Dictionary<string, string>> callback)
    {
        // Create the URL with arguments
        string url = BASE_URL + endpoint;
        if (args != null && args.Count > 0)
        {
            url += "?";
            foreach (var arg in args)
            {
                url += $"{arg.Key}={arg.Value}&";
            }
            url = url.TrimEnd('&');
        }
        Debug.Log(url);

        using (UnityWebRequest webRequest = UnityWebRequest.Get(url))
        {
            // Send the request
            yield return webRequest.SendWebRequest();

            // Check for errors
            if (webRequest.result == UnityWebRequest.Result.ConnectionError || webRequest.result == UnityWebRequest.Result.ProtocolError)
            {
                Debug.LogError($"Error while requesting {url}: {webRequest.error}");
                yield break;
            }

            // Parse the response and call the callback
            string responseJson = webRequest.downloadHandler.text;
            Debug.Log($"Response: {responseJson}");
            Dictionary<string, string> responseArgs = new Dictionary<string, string>();
            if (responseJson != null && responseJson.Length > 0)
            {
                responseArgs = Newtonsoft.Json.JsonConvert.DeserializeObject<Dictionary<string, string>>(responseJson);
            }
            callback?.Invoke(responseArgs);
        }
    }
}
