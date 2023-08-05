using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class GameDisplayer : MonoBehaviour
{
    public GameObject shipPrefab;

    private Dictionary<string, Ship> uuidsToShips = new();
    private Dictionary<Vector2Int, bool> occupiedDict = new();

    private string myCurrentShipUuid;

    private void OnEnable()
    {
        ServerPinger.OnZoneStateReceived += DisplayZone;
    }

    // Start is called before the first frame update
    void Start()
    {
        
    }

    // Update is called once per frame
    void Update()
    {
        
    }

    public Tuple<string, Vector2Int> GetFacingAndPosition(string uuid)
    {
        Ship ship = uuidsToShips[uuid];
        return new Tuple<string, Vector2Int>(ship.GetFacing(), ship.GetPosition());
    }

    public List<string> GetActionsToReachPoint(string myShipUuid, Vector2Int startingPoint, string startingFacing, Vector2Int targetPoint, string targetFacing)
    {
        string currentFacing = startingFacing;
        Vector2Int currentPoint = startingPoint;
        HashSet<Tuple<string, Vector2Int>> explored = new(); // (facing, position)
        Queue<Tuple<string, Vector2Int>> frontier = new();
        frontier.Enqueue(new Tuple<string, Vector2Int>(currentFacing, currentPoint));
        Dictionary<Tuple<string, Vector2Int>, Tuple<string, Vector2Int>> cameFrom = new();

        // use breadth first search to find the shortest path from current position and facing to target position and facing
        while (frontier.Count > 0)
        {
            Tuple<string, Vector2Int> current = frontier.Dequeue();
            if (current.Item2 == targetPoint && current.Item1 == targetFacing)
            {
                // found the target
                break;
            }
            if (explored.Contains(current))
            {
                continue;
            }
            explored.Add(current);
            // add neighbors to frontier
            foreach (Tuple<string, Vector2Int> neighbor in GetNeighbors(current))
            {
                frontier.Enqueue(neighbor);
                cameFrom[neighbor] = current;
            }
        }

        // reconstruct the path
        List<Tuple<string, Vector2Int>> path = new();
        Tuple<string, Vector2Int> step = new Tuple<string, Vector2Int>(targetFacing, targetPoint);
        while (step != null)
        {
            path.Add(step);
            step = cameFrom.GetValueOrDefault(step, null);
        }
        path.Reverse();
        // convert path to list of actions: "left" for left turn, "right" for right turn, "step" for forward
        List<string> actions = new();
        for (int i = 1; i < path.Count; i++)
        {
            Tuple<string, Vector2Int> previous = path[i - 1];
            Tuple<string, Vector2Int> current = path[i];
            if (previous.Item1 == current.Item1)
            {
                actions.Add("step");
            }
            else if (GetLeftFacing(previous.Item1) == current.Item1)
            {
                actions.Add("left");
            }
            else if (GetRightFacing(previous.Item1) == current.Item1)
            {
                actions.Add("right");
            }
            else
            {
                throw new Exception("Invalid path");
            }
        }
        return actions;
    }

    private List<Tuple<string, Vector2Int>> GetNeighbors(Tuple<string, Vector2Int> current)
    {
        // options are turn left, turn right, and go forward if not blocked accordign to occupiedDict
        List<Tuple<string, Vector2Int>> neighbors = new();
        Vector2Int forward = current.Item2 + GetFacingVector(current.Item1);
        if (!occupiedDict.ContainsKey(forward))
        {
            neighbors.Add(new Tuple<string, Vector2Int>(current.Item1, forward));
        }
        string leftFacing = GetLeftFacing(current.Item1);
        neighbors.Add(new Tuple<string, Vector2Int>(leftFacing, current.Item2));
        string rightFacing = GetRightFacing(current.Item1);
        neighbors.Add(new Tuple<string, Vector2Int>(rightFacing, current.Item2));
        return neighbors;
    }

    public static string GetRightFacing(string currentFacing)
    {
        return currentFacing switch
        {
            "N" => "E",
            "S" => "W",
            "E" => "S",
            "W" => "N",
            _ => throw new Exception("Invalid currentFacing: " + currentFacing),
        };
    }

    public static string GetLeftFacing(string currentFacing)
    {
        return currentFacing switch
        {
            "N" => "W",
            "S" => "E",
            "E" => "N",
            "W" => "S",
            _ => throw new Exception("Invalid currentFacing: " + currentFacing),
        };
    }

    public static Vector2Int GetFacingVector(string facing)
    {
        return facing switch
        {
            "N" => new Vector2Int(0, 1),
            "S" => new Vector2Int(0, -1),
            "E" => new Vector2Int(1, 0),
            "W" => new Vector2Int(-1, 0),
            _ => throw new Exception("Invalid facing: " + facing),
        };
    }

    public void DisplayActionQueue(string actionQueue, string myShipUuid)
    {
        // TODO
    }

    private void DisplayZone(Dictionary<string, string> args, string myShipUuid)
    {
        Debug.Log("Displaying zone");
        myCurrentShipUuid = myShipUuid;
        occupiedDict.Clear();
        for (int i = 0; i < 50; i++)
        {
            for (int j = 0; j < 50; j++)
            {
                if (args.ContainsKey(i + "," + j + ",type"))
                {
                    Debug.Log("Found ship at " + i + "," + j);
                    //string type = args[i + "," + j + ",type"];
                    string uuid = args[i + "," + j + ",uuid"];
                    string facing = args[i + "," + j + ",facing"];
                    Vector2Int position = new Vector2Int(i, j);
                    occupiedDict[position] = true;
                    Ship ship;
                    if (uuidsToShips.ContainsKey(uuid))
                    {
                        ship = uuidsToShips[uuid];
                        ship.DisplayUpdate(position, facing);
                    }
                    else
                    {
                        GameObject shipObject = Instantiate(shipPrefab, new Vector3(position.x, position.y, 0), Quaternion.identity);
                        shipObject.GetComponent<Ship>().Initialize(position, facing);
                        ship = shipObject.GetComponent<Ship>();
                        uuidsToShips.Add(uuid, ship);
                    }
                    if (uuid == myShipUuid)
                    {
                        // follow with camera
                        Camera.main.transform.position = new Vector3(ship.transform.position.x, ship.transform.position.y, -10);
                    }
                }
            }
        }
    }
}
