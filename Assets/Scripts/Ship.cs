using System.Collections;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using UnityEngine;
using UnityEngine.UIElements.Experimental;

public class Ship : MonoBehaviour
{
    private Vector2Int gamePosition;
    private string gameRotation;

    public string GetFacing()
    {
        return gameRotation;
    }

    public Vector2Int GetPosition()
    {
        return gamePosition;
    }

    public void Initialize(Vector2Int newGamePosition, string newGameRotation)
    {
        gamePosition = newGamePosition;
        gameRotation = newGameRotation;
        Ship.Initialize(this.gameObject, newGameRotation, newGamePosition);
    }

    public static void Initialize(GameObject ship, string newGameRotation, Vector2Int newGamePosition)
    {        
        ship.transform.transform.position = new Vector3(newGamePosition.x, newGamePosition.y, 0);

        if (newGameRotation == "N")
        {
            ship.transform.eulerAngles = new Vector3(0, 0, 0);
        }
        else if (newGameRotation == "S")
        {
            ship.transform.eulerAngles = new Vector3(0, 0, -180);
        }
        else if (newGameRotation == "W")
        {
            ship.transform.eulerAngles = new Vector3(0, 0, 90);
        }
        else if (newGameRotation == "E")
        {
            ship.transform.eulerAngles = new Vector3(0, 0, 270);
        }
    }

    public void DisplayUpdate(Vector2Int newGamePosition, string newGameRotation)
    {
        Initialize(newGamePosition, newGameRotation);
    }
}
